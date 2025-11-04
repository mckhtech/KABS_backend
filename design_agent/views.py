import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from .models import Project, PDFDocument, PDFPage, Extraction, SKUMatch, Render, Annotation, Pricing
from .serializers import (
    ProjectSerializer, 
    PDFDocumentSerializer,
    ExtractionSerializer,
    SKUMatchSerializer,
    RenderSerializer
)
from .tasks import (
    process_pdf_to_images,
    extract_all_pages_for_pdf,
    match_skus_for_extraction,
    generate_all_renders_for_project
)
from .services.pdf_generator import generate_project_pdf
from django.http import HttpResponse
from datetime import datetime

logger = logging.getLogger('design_agent')


class ProjectViewSet(viewsets.ModelViewSet):
    """
    Main project management
    
    Endpoints:
    - POST /api/projects/ - Create new project
    - GET /api/projects/ - List all projects
    - GET /api/projects/{id}/ - Get project details
    """
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter projects by current user"""
        return Project.objects.filter(
            created_by=self.request.user,
            is_active=True
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Associate with current user"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_pdf(self, request, pk=None):
        """
        POST /api/projects/{id}/upload_pdf/
        
        Stage 1: PDF Ingestion (ASYNC with Celery)
        Upload PDF file and queue conversion to images
        
        Request:
            - file: PDF file (multipart/form-data)
        
        Response:
            {
                "pdf_id": "uuid",
                "filename": "kitchen_design.pdf",
                "status": "queued",
                "task_id": "celery-task-id",
                "message": "PDF queued for processing"
            }
        """
        project = self.get_object()
        
        try:
            # Check if file was uploaded
            if 'file' not in request.FILES:
                return Response(
                    {'error': 'No file provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            pdf_file = request.FILES['file']
            
            # Validate file type
            if not pdf_file.name.endswith('.pdf'):
                return Response(
                    {'error': 'File must be a PDF'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Delete existing PDF if exists
            if hasattr(project, 'pdf_document'):
                old_pdf = project.pdf_document
                old_pdf.delete()
            
            # Create PDF document
            pdf_document = PDFDocument.objects.create(
                project=project,
                file=pdf_file,
                filename=pdf_file.name,
                processing_status='queued'
            )
            
            # Queue conversion task
            task = process_pdf_to_images.delay(str(pdf_document.id))
            
            logger.info(f"Queued PDF conversion for project {project.id}: task {task.id}")
            
            return Response({
                'pdf_id': str(pdf_document.id),
                'filename': pdf_document.filename,
                'status': 'queued',
                'task_id': task.id,
                'message': 'PDF uploaded and queued for processing'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error uploading PDF: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def files(self, request, pk=None):
        """
        GET /api/projects/{id}/files/
        
        Fetch PDF info and all generated images
        
        Response:
            {
                "pdf": {
                    "id": "uuid",
                    "filename": "kitchen.pdf",
                    "page_count": 3,
                    "status": "completed"
                },
                "pages": [
                    {
                        "page_number": 1,
                        "image_url": "http://..."
                    }
                ]
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded for this project'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        pdf_document = project.pdf_document
        pdf_pages = pdf_document.pages.all().order_by('page_number')
        
        return Response({
            'pdf': {
                'id': str(pdf_document.id),
                'filename': pdf_document.filename,
                'page_count': pdf_document.page_count,
                'status': pdf_document.processing_status
            },
            'pages': [
                {
                    'page_number': page.page_number,
                    'image_url': request.build_absolute_uri(page.image_file.url) if page.image_file else None
                }
                for page in pdf_pages
            ]
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def extract_layout(self, request, pk=None):
        """
        POST /api/projects/{id}/extract_layout/
        
        Stage 2: Extraction (ASYNC with Celery)
        Queue extraction for all pages using Claude
        
        Response:
            {
                "status": "queued",
                "pages_queued": 3,
                "task_id": "celery-task-id",
                "message": "Extraction queued for 3 pages"
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pdf_document = project.pdf_document
        
        if pdf_document.processing_status != 'completed':
            return Response(
                {'error': f'PDF is still processing (status: {pdf_document.processing_status})'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Queue extraction for all pages
            task = extract_all_pages_for_pdf.delay(str(pdf_document.id))
            
            page_count = pdf_document.pages.count()
            logger.info(f"Queued extraction for {page_count} pages: task {task.id}")
            
            return Response({
                'status': 'queued',
                'pages_queued': page_count,
                'task_id': task.id,
                'message': f'Extraction queued for {page_count} pages'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error queueing extraction: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def extraction_results(self, request, pk=None):
        """
        GET /api/projects/{id}/extraction_results/
        
        Fetch extraction results after they're done
        
        Response:
            {
                "extractions": [
                    {
                        "page": 1,
                        "status": "completed",
                        "view_type": "elevation",
                        "items_found": 15,
                        "items": [...]
                    }
                ]
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pdf_document = project.pdf_document
        extractions = Extraction.objects.filter(
            pdf_page__pdf_document=pdf_document
        ).select_related('pdf_page').order_by('pdf_page__page_number')
        
        if not extractions.exists():
            return Response(
                {'error': 'No extractions found. Run extract_layout first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        response_data = {
            'project_id': str(project.id),
            'total_pages': extractions.count(),
            'extractions': []
        }
        
        for extraction in extractions:
            response_data['extractions'].append({
                'page': extraction.pdf_page.page_number,
                'status': extraction.status,
                'view_type': extraction.structured_data.get('view_type'),
                'items_found': len(extraction.structured_data.get('items', [])),
                'items': extraction.structured_data.get('items', [])
            })
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def match_skus(self, request, pk=None):
        """
        POST /api/projects/{id}/match_skus/
        
        Stage 3: SKU Matching (SYNC - fast PostgreSQL queries)
        Match extracted labels to SKUs in database
        
        Request (optional):
            {
                "dimension_tolerance": 2.0  // inches (default: 2.0)
            }
        
        Response:
            {
                "matched_items": [...]
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .services.sku_matcher import SKUMatcher
            
            # Get all extractions
            pdf_document = project.pdf_document
            extractions = Extraction.objects.filter(
                pdf_page__pdf_document=pdf_document,
                status='completed'
            )
            
            if not extractions.exists():
                return Response(
                    {'error': 'No completed extractions found. Run extract_layout first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get tolerance from request
            tolerance = request.data.get('dimension_tolerance', 5.0)
            
            # Match SKUs for each extraction (fast sync operation)
            matcher = SKUMatcher(dimension_tolerance=tolerance)
            all_matches = []
            
            for extraction in extractions:
                matches = matcher.match_extraction(extraction)
                all_matches.extend(matches)
            
            logger.info(f"Matched {len(all_matches)} items for project {project.id}")
            
            # Serialize response
            response_data = {
                'project_id': str(project.id),
                'total_matched': len(all_matches),
                'matched_items': []
            }
            
            for match in all_matches:
                response_data['matched_items'].append({
                    'page': match.extraction.pdf_page.page_number,
                    'label': match.label_text,
                    'matched_sku': {
                        'code': match.matched_sku.code,
                        'name': match.matched_sku.name,
                        'image_url': request.build_absolute_uri(match.matched_sku.image.url) if match.matched_sku.image else None,
                        'dimensions': {
                            'width': float(match.matched_sku.width) if match.matched_sku.width else None,
                            'height': float(match.matched_sku.height) if match.matched_sku.height else None,
                            'depth': float(match.matched_sku.depth) if match.matched_sku.depth else None
                        }
                    },
                    'match_score': match.match_score,
                    'alternatives': match.alternative_skus
                })
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error matching SKUs: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def generate_renders(self, request, pk=None):
        """
        POST /api/projects/{id}/generate_renders/
        
        Stage 6: Rendering (ASYNC with Celery)
        Queue photorealistic render generation using Gemini
        
        Request:
            {
                "style": "modern"  // "modern", "traditional", "minimalist"
            }
        
        Response:
            {
                "status": "queued",
                "pages_queued": 3,
                "task_id": "celery-task-id"
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Check if SKU matching is done
            pdf_document = project.pdf_document
            sku_matches = SKUMatch.objects.filter(
                extraction__pdf_page__pdf_document=pdf_document
            )
            
            if not sku_matches.exists():
                return Response(
                    {'error': 'No SKU matches found. Run match_skus first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get style preference
            style = request.data.get('style', 'modern')
            
            if style not in ['modern', 'traditional', 'minimalist']:
                return Response(
                    {'error': 'Invalid style. Must be: modern, traditional, or minimalist'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Queue render generation
            task = generate_all_renders_for_project.delay(
                str(project.id),
                style_preference=style
            )
            
            page_count = pdf_document.pages.count()
            logger.info(f"Queued {page_count} renders for project {project.id}: task {task.id}")
            
            return Response({
                'status': 'queued',
                'pages_queued': page_count,
                'style': style,
                'task_id': task.id,
                'message': f'Render generation queued for {page_count} pages'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error queueing renders: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def renders(self, request, pk=None):
        """
        GET /api/projects/{id}/renders/
        
        Fetch all renders for the project
        
        Response:
            {
                "renders": [
                    {
                        "page": 1,
                        "render_id": "uuid",
                        "status": "completed",
                        "image_url": "http://...",
                        "generation_time": 45.2
                    }
                ]
            }
        """
        project = self.get_object()
        
        renders = Render.objects.filter(project=project).select_related('pdf_page').order_by('pdf_page__page_number')
        
        if not renders.exists():
            return Response(
                {'error': 'No renders found. Run generate_renders first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        response_data = {
            'project_id': str(project.id),
            'total_renders': renders.count(),
            'renders': []
        }
        
        for render in renders:
            render_data = {
                'page': render.pdf_page.page_number,
                'render_id': str(render.id),
                'status': render.status,
                'style': render.style_preference,
                'generation_time': render.generation_time,
                'created_at': render.created_at
            }
            
            if render.status == 'completed' and render.image_file:
                render_data['image_url'] = request.build_absolute_uri(render.image_file.url)
            elif render.status == 'failed':
                render_data['error'] = render.error_message
            
            response_data['renders'].append(render_data)
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        GET /api/projects/{id}/status/
        
        Get complete project status - shows progress through all stages
        """
        project = self.get_object()
        
        status_data = {
            'project_id': str(project.id),
            'name': project.name,
            'project_type': project.project_type,
            'created_at': project.created_at,
            'stages': {
                'pdf_uploaded': False,
                'pdf_status': None,
                'extraction_completed': False,
                'status': None,
                'skus_matched': False,
                'renders_generated': False,
                'renders_status': None
            }
        }
        
        # Check PDF upload
        if hasattr(project, 'pdf_document'):
            pdf_doc = project.pdf_document
            status_data['stages']['pdf_uploaded'] = True
            status_data['stages']['pdf_status'] = pdf_doc.processing_status
            status_data['pdf'] = {
                'filename': pdf_doc.filename,
                'page_count': pdf_doc.page_count,
                'status': pdf_doc.processing_status
            }
            
            # Check extractions
            extractions = Extraction.objects.filter(
                pdf_page__pdf_document=pdf_doc
            )
            if extractions.exists():
                completed = extractions.filter(status='completed').count()
                total = extractions.count()
                
                status_data['stages']['extraction_completed'] = (completed == total)
                status_data['stages']['status'] = f'{completed}/{total} completed'
                status_data['extractions'] = {
                    'total_pages': total,
                    'completed': completed,
                    'processing': extractions.filter(status='processing').count(),
                    'failed': extractions.filter(status='failed').count()
                }
                
                # Check SKU matches
                sku_matches = SKUMatch.objects.filter(
                    extraction__pdf_page__pdf_document=pdf_doc
                )
                if sku_matches.exists():
                    status_data['stages']['skus_matched'] = True
                    status_data['sku_matches'] = {
                        'total_matched': sku_matches.count()
                    }
                    
                    # Check renders
                    renders = Render.objects.filter(project=project)
                    if renders.exists():
                        completed_renders = renders.filter(status='completed').count()
                        total_renders = renders.count()
                        
                        status_data['stages']['renders_generated'] = (completed_renders > 0)
                        status_data['stages']['renders_status'] = f'{completed_renders}/{total_renders} completed'
                        status_data['renders'] = {
                            'total': total_renders,
                            'completed': completed_renders,
                            'processing': renders.filter(status='processing').count(),
                            'queued': renders.filter(status='queued').count(),
                            'failed': renders.filter(status='failed').count()
                        }
        
        return Response(status_data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'])
    def download_report(self, request, pk=None):
        """
        GET /api/projects/{id}/download_report/
        
        Generate and download final PDF report
        
        Response:
            PDF file download
        """
        project = self.get_object()
        
        # Validate project has required data
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not hasattr(project, 'pricing'):
            return Response(
                {'error': 'No pricing generated. Run generate_pricing first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        renders = project.renders.filter(status='completed')
        if not renders.exists():
            return Response(
                {'error': 'No completed renders. Run generate_renders first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if project.pdf_document and project.pdf_document.file.size == 0:
            return Response(
                {'error': 'Uploaded PDF is empty or corrupt.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        
        try:
            # Generate PDF
            pdf_buffer = generate_project_pdf(project)
            
            # Create HTTP response
            response = HttpResponse(
                pdf_buffer.read(),
                content_type='application/pdf'
            )
            
            filename = f"design_proposal_{project.name.replace(' ', '_')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"Generated PDF report for project {project.id}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            return Response(
                {'error': f'Failed to generate report: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """
        GET /api/projects/{id}/summary/
        
        Get complete project summary (all stages)
        
        Response:
            {
                "project": {...},
                "extraction_summary": {...},
                "sku_matches": {...},
                "pricing": {...},
                "renders": {...}
            }
        """
        project = self.get_object()
        
        summary_data = {
            'project_id': str(project.id),
            'name': project.name,
            'project_type': project.project_type,
            'created_at': project.created_at,
            'updated_at': project.updated_at,
            'stages_completed': []
        }
        
        # PDF Upload stage
        if hasattr(project, 'pdf_document'):
            pdf_doc = project.pdf_document
            summary_data['pdf'] = {
                'filename': pdf_doc.filename,
                'pages': pdf_doc.page_count,
                'status': pdf_doc.processing_status
            }
            summary_data['stages_completed'].append('pdf_upload')
            
            # Extraction stage
            extractions = pdf_doc.pages.filter(extraction__isnull=False)
            if extractions.exists():
                total_items = 0
                for page in extractions:
                    items = page.extraction.structured_data.get('items', [])
                    total_items += len(items)
                
                summary_data['extraction'] = {
                    'pages_extracted': extractions.count(),
                    'total_items': total_items,
                    'status': 'completed' if extractions.count() == pdf_doc.page_count else 'partial'
                }
                summary_data['stages_completed'].append('extraction')
                
                # SKU Matching stage
                sku_matches = SKUMatch.objects.filter(
                    extraction__pdf_page__pdf_document=pdf_doc
                )
                if sku_matches.exists():
                    summary_data['sku_matching'] = {
                        'total_matches': sku_matches.count(),
                        'average_score': sum(m.match_score for m in sku_matches) / sku_matches.count()
                    }
                    summary_data['stages_completed'].append('sku_matching')
        
        # Pricing stage
        if hasattr(project, 'pricing'):
            pricing = project.pricing
            summary_data['pricing'] = {
                'status': pricing.status,
                'total_items': project.pricing_items.count(),
                'subtotal': str(pricing.subtotal),
                'total': str(pricing.total),
                'is_locked': pricing.status == 'locked'
            }
            summary_data['stages_completed'].append('pricing')
        
        # Rendering stage
        renders = project.renders.all()
        if renders.exists():
            completed = renders.filter(status='completed').count()
            summary_data['rendering'] = {
                'total_renders': renders.count(),
                'completed': completed,
                'failed': renders.filter(status='failed').count(),
                'average_time': sum(r.generation_time or 0 for r in renders) / renders.count()
            }
            if completed > 0:
                summary_data['stages_completed'].append('rendering')
        
        # Overall completion
        total_stages = 5  # pdf, extraction, sku_matching, pricing, rendering
        summary_data['completion_percentage'] = (len(summary_data['stages_completed']) / total_stages) * 100
        summary_data['is_complete'] = len(summary_data['stages_completed']) == total_stages
        
        return Response(summary_data, status=status.HTTP_200_OK)
    

    @action(detail=True, methods=['get'])
    def validate_skus(self, request, pk=None):
        """
        GET /api/projects/{id}/validate_skus/
        
        Validate SKU data completeness before rendering
        
        Response:
            {
                "valid": true,
                "can_render": true,
                "total_skus": 40,
                "unique_skus": 35,
                "skus_with_images": 38,
                "skus_with_prices": 40,
                "missing_images": [
                    {
                        "sku_code": "DB18-3",
                        "sku_name": "Drawer Base 18",
                        "pages": [1, 2],
                        "category": "base_cabinet"
                    }
                ],
                "missing_prices": [],
                "validation_summary": "2 SKUs missing images",
                "recommendations": [
                    "Upload images for 2 SKUs to improve render quality",
                    "Renders will still generate but may use generic placeholders"
                ]
            }
        """
        project = self.get_object()
        
        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .services.sku_validation import SKUValidator
            
            validator = SKUValidator()
            validation_results = validator.validate_project_skus(project)
            
            return Response(validation_results, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error validating SKUs: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @action(detail=True, methods=['get'])
    def report_data(self, request, pk=None):
        """
        GET /api/projects/{id}/report_data/
        
        Get complete report data in JSON format (same data as PDF report)
        This endpoint provides all information needed to render the report
        in any format (PDF, web view, email, etc.)
        
        Response:
            {
                "project": {
                    "id": "uuid",
                    "name": "Prisha new",
                    "project_type": "kitchen",
                    "created_at": "2025-10-28T...",
                    "created_by": {
                        "username": "newuser",
                        "full_name": "newuser test1"
                    }
                },
                "statistics": {
                    "pages_analyzed": 3,
                    "components_identified": 44,
                    "renderings_generated": 2
                },
                "pdf_document": {
                    "id": "uuid",
                    "filename": "kitchen_design.pdf",
                    "page_count": 3,
                    "pages": [
                        {
                            "page_number": 1,
                            "image_url": "http://..."
                        }
                    ]
                },
                "renders": [
                    {
                        "page": 2,
                        "render_id": "uuid",
                        "status": "completed",
                        "style": "modern",
                        "image_url": "http://...",
                        "generation_time": 24.8,
                        "created_at": "2025-10-28T..."
                    }
                ],
                "specifications": {
                    "by_category": {
                        "cabinet": [
                            {
                                "sku_code": "B09R",
                                "sku_name": "Base Cabinet 9 Right",
                                "category": "cabinet",
                                "dimensions": {
                                    "width": 9.0,
                                    "height": 34.5,
                                    "depth": 24.0
                                },
                                "finish": "white",
                                "quantity": 1,
                                "unit_price": "400.00",
                                "total_price": "400.00",
                                "image_url": "http://..."
                            }
                        ],
                        "appliance": [...]
                    },
                    "total_items": 44
                },
                "pricing": {
                    "status": "draft",
                    "line_items": [
                        {
                            "item_name": "Base Cabinet 9 Right",
                            "sku_code": "B09R",
                            "quantity": 1,
                            "unit_price": "400.00",
                            "discount": "0.00",
                            "final_price": "400.00"
                        }
                    ],
                    "subtotal": "16500.00",
                    "total_discount": "0.00",
                    "tax_rate": "0.00",
                    "tax_amount": "0.00",
                    "total": "16500.00",
                    "payment_terms": "50% deposit required, balance due upon completion. Prices valid for 30 days."
                },
                "annotations": {
                    "special_cabinets": [
                        {
                            "page": 1,
                            "sku_code": "DB18-3",
                            "text": "Special drawer configuration required",
                            "created_by": "designer1",
                            "created_at": "2025-10-28T..."
                        }
                    ],
                    "comments": [],
                    "change_requests": []
                },
                "generated_at": "2025-10-28T19:40:00Z",
                "report_metadata": {
                    "version": "1.0",
                    "can_download_pdf": true,
                    "is_complete": true,
                    "completion_percentage": 100
                }
            }
        """
        project = self.get_object()
        
        try:
            # Build comprehensive report data
            report_data = {
                "project": {
                    "id": str(project.id),
                    "name": project.name,
                    "project_type": project.project_type,
                    "project_type_display": project.get_project_type_display(),
                    "created_at": project.created_at.isoformat(),
                    "updated_at": project.updated_at.isoformat(),
                    "created_by": {
                        "username": project.created_by.username,
                        "full_name": project.created_by.get_full_name() or project.created_by.username,
                        "email": project.created_by.email
                    }
                }
            }
            
            # PDF Document Info
            if hasattr(project, 'pdf_document') and project.pdf_document:
                pdf_doc = project.pdf_document
                pdf_pages = pdf_doc.pages.all().order_by('page_number')
                
                report_data['pdf_document'] = {
                    "id": str(pdf_doc.id),
                    "filename": pdf_doc.filename,
                    "page_count": pdf_doc.page_count,
                    "processing_status": pdf_doc.processing_status,
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "image_url": request.build_absolute_uri(page.image_file.url) if page.image_file else None
                        }
                        for page in pdf_pages
                    ]
                }
                
                # Statistics
                extractions = pdf_doc.pages.count()
                sku_matches = 0
                if hasattr(project, 'pricing') and project.pricing:
                    sku_matches = project.pricing.items.count()
                
                report_data['statistics'] = {
                    "pages_analyzed": extractions,
                    "components_identified": sku_matches,
                    "renderings_generated": project.renders.filter(status='completed', is_active=True).count()
                }
            else:
                report_data['pdf_document'] = None
                report_data['statistics'] = {
                    "pages_analyzed": 0,
                    "components_identified": 0,
                    "renderings_generated": 0
                }
            
            # Renders
            renders = Render.objects.filter(
                project=project,
                status='completed',
                is_active=True
            ).select_related('pdf_page').order_by('pdf_page__page_number')
            
            report_data['renders'] = []
            for render in renders:
                render_data = {
                    "page": render.pdf_page.page_number,
                    "render_id": str(render.id),
                    "status": render.status,
                    "style": render.style_preference,
                    "generation_time": float(render.generation_time) if render.generation_time else None,
                    "created_at": render.created_at.isoformat()
                }
                if render.image_file:
                    render_data['image_url'] = request.build_absolute_uri(render.image_file.url)
                report_data['renders'].append(render_data)
            
            # Specifications (grouped by category)
            if hasattr(project, 'pricing') and project.pricing:
                line_items = project.pricing.items.select_related('sku_match__matched_sku').all()
                
                specifications = {
                    "by_category": {},
                    "total_items": 0
                }
                
                for item in line_items:
                    if item.sku_match and item.sku_match.matched_sku:
                        sku = item.sku_match.matched_sku
                        category = sku.category
                        
                        if category not in specifications['by_category']:
                            specifications['by_category'][category] = []
                        
                        sku_data = {
                            "sku_code": sku.code,
                            "sku_name": sku.name,
                            "category": category,
                            "dimensions": {
                                "width": float(sku.width) if sku.width else None,
                                "height": float(sku.height) if sku.height else None,
                                "depth": float(sku.depth) if sku.depth else None
                            },
                            "finish": sku.finish or "Standard",
                            "quantity": item.quantity,
                            "unit_price": str(item.unit_price),
                            "total_price": str(item.final_price),
                            "image_url": request.build_absolute_uri(sku.image.url) if sku.image else None,
                            "description": sku.description or ""
                        }
                        
                        specifications['by_category'][category].append(sku_data)
                        specifications['total_items'] += 1
                
                report_data['specifications'] = specifications
            else:
                report_data['specifications'] = {
                    "by_category": {},
                    "total_items": 0
                }
            
            # Pricing
            if hasattr(project, 'pricing') and project.pricing:
                pricing = project.pricing
                line_items = pricing.items.all()
                
                report_data['pricing'] = {
                    "status": pricing.status,
                    "line_items": [
                        {
                            "item_name": item.sku_name,
                            "sku_code": item.sku_code,
                            "quantity": item.quantity,
                            "unit_price": str(item.unit_price),
                            "discount_percentage": str(item.discount_percentage) if item.discount_percentage else "0.00",
                            "discount_amount": str(item.discount_amount) if item.discount_amount else "0.00",
                            "subtotal": str(item.subtotal) if hasattr(item, 'subtotal') else str(item.unit_price * item.quantity),
                            "final_price": str(item.final_price),
                            "notes": item.notes or ""
                        }
                        for item in line_items
                    ],
                    "subtotal": str(pricing.subtotal),
                    "total_discount": str(pricing.total_discount) if pricing.total_discount else "0.00",
                    "tax_rate": str(pricing.tax_rate) if pricing.tax_rate else "0.00",
                    "tax_amount": str(pricing.tax_amount) if pricing.tax_amount else "0.00",
                    "total": str(pricing.total),
                    "payment_terms": "50% deposit required, balance due upon completion. Prices valid for 30 days from proposal date.",
                    "is_locked": pricing.status == 'locked',
                    "created_at": pricing.created_at.isoformat(),
                    "updated_at": pricing.updated_at.isoformat()
                }
            else:
                report_data['pricing'] = None
            
            # Annotations
            annotations = Annotation.objects.filter(
                render__project=project
            ).select_related('render__pdf_page', 'created_by').order_by('render__pdf_page__page_number', 'created_at')
            
            annotations_data = {
                "special_cabinets": [],
                "comments": [],
                "change_requests": []
            }
            
            for annotation in annotations:
                ann_data = {
                    "id": str(annotation.id),
                    "page": annotation.render.pdf_page.page_number,
                    "sku_code": annotation.sku_code or "",
                    "text": annotation.text,
                    "created_by": annotation.created_by.username,
                    "created_at": annotation.created_at.isoformat()
                }
                
                if annotation.annotation_type == 'special_cabinet':
                    annotations_data['special_cabinets'].append(ann_data)
                elif annotation.annotation_type == 'comment':
                    annotations_data['comments'].append(ann_data)
                elif annotation.annotation_type == 'change_request':
                    annotations_data['change_requests'].append(ann_data)
            
            report_data['annotations'] = annotations_data
            
            # Metadata
            can_download_pdf = (
                hasattr(project, 'pdf_document') and 
                hasattr(project, 'pricing') and 
                project.renders.filter(status='completed').exists()
            )
            
            # Calculate completion
            stages_completed = []
            if hasattr(project, 'pdf_document'):
                stages_completed.append('pdf_upload')
                if project.pdf_document.pages.filter(extraction__isnull=False).exists():
                    stages_completed.append('extraction')
                    from design_agent.models import SKUMatch
                    if SKUMatch.objects.filter(extraction__pdf_page__pdf_document=project.pdf_document).exists():
                        stages_completed.append('sku_matching')
            if hasattr(project, 'pricing'):
                stages_completed.append('pricing')
            if project.renders.filter(status='completed').exists():
                stages_completed.append('rendering')
            
            total_stages = 5
            completion_percentage = (len(stages_completed) / total_stages) * 100
            
            report_data['report_metadata'] = {
                "version": "1.0",
                "can_download_pdf": can_download_pdf,
                "is_complete": len(stages_completed) == total_stages,
                "completion_percentage": completion_percentage,
                "stages_completed": stages_completed,
                "generated_at": datetime.now().isoformat()
            }
            
            logger.info(f"Generated report data for project {project.id}")
            return Response(report_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error generating report data: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return Response(
                {'error': f'Failed to generate report data: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )