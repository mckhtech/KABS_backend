# design_agent/preview_3d_views.py
"""
API endpoints for 3D preview generation (testing)
Standalone endpoints for validation before integration
"""

import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Project, PDFPage, Extraction, SKUMatch
from .services.preview_3d_renderer import Gemini3DPreviewRenderer

logger = logging.getLogger('design_agent')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_3d_preview(request, project_id, page_number):
    """
    POST /api/projects/{project_id}/pages/{page_number}/generate_3d_preview/
    
    Generate simple 3D preview for a specific page
    
    Request (optional):
        {
            "include_sku_labels": true  // default: true if SKU matches exist
        }
    
    Response:
        {
            "success": true,
            "page_number": 2,
            "image_url": "http://.../media/3d_previews/...",
            "generation_time": 15.3,
            "sku_count": 12,
            "message": "3D preview generated successfully"
        }
    
    OR (if failed):
        {
            "success": false,
            "error": "Error message",
            "page_number": 2
        }
    """
    try:
        # Get project and verify ownership
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check if PDF uploaded
        if not hasattr(project, 'pdf_document'):
            return Response(
                {
                    'success': False,
                    'error': 'No PDF uploaded for this project'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get specific page
        try:
            pdf_page = project.pdf_document.pages.get(page_number=page_number)
        except PDFPage.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'error': f'Page {page_number} not found'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get extraction data
        if not hasattr(pdf_page, 'extraction'):
            return Response(
                {
                    'success': False,
                    'error': f'No extraction data for page {page_number}. Run extract_layout first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        extraction = pdf_page.extraction
        
        # Get SKU matches (optional)
        include_skus = request.data.get('include_sku_labels', True)
        sku_matches = None
        sku_count = 0
        
        if include_skus:
            sku_matches = list(extraction.sku_matches.all())
            sku_count = len(sku_matches)
            logger.info(f"Including {sku_count} SKU labels in 3D preview")
        
        # Generate 3D preview
        renderer = Gemini3DPreviewRenderer()
        result = renderer.generate_3d_preview(
            pdf_page=pdf_page,
            extraction=extraction,
            sku_matches=sku_matches
        )
        
        if result['success']:
            # Build absolute URL
            image_url = request.build_absolute_uri(result['image_path'])
            
            return Response({
                'success': True,
                'page_number': page_number,
                'image_url': image_url,
                'generation_time': result['generation_time'],
                'sku_count': sku_count,
                'view_type': extraction.structured_data.get('view_type', 'unknown'),
                'message': '3D preview generated successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': result.get('error', 'Unknown error'),
                'page_number': page_number
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Project.DoesNotExist:
        return Response(
            {
                'success': False,
                'error': 'Project not found or access denied'
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        logger.error(f"Error generating 3D preview: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return Response(
            {
                'success': False,
                'error': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def batch_generate_3d_previews(request, project_id):
    """
    POST /api/projects/{project_id}/generate_all_3d_previews/
    
    Generate 3D previews for ALL elevation pages in project
    Skips floor plans automatically
    
    Request (optional):
        {
            "include_sku_labels": true
        }
    
    Response:
        {
            "success": true,
            "total_pages": 3,
            "generated": 2,
            "skipped": 1,
            "failed": 0,
            "results": [
                {
                    "page_number": 2,
                    "success": true,
                    "image_url": "http://...",
                    "generation_time": 15.3
                },
                {
                    "page_number": 3,
                    "success": true,
                    "image_url": "http://...",
                    "generation_time": 14.8
                },
                {
                    "page_number": 1,
                    "success": false,
                    "reason": "Floor plan - skipped"
                }
            ],
            "total_time": 30.1
        }
    """
    try:
        import time
        
        # Get project and verify ownership
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check if PDF uploaded
        if not hasattr(project, 'pdf_document'):
            return Response(
                {
                    'success': False,
                    'error': 'No PDF uploaded for this project'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pdf_document = project.pdf_document
        
        # Get all pages with extractions
        pdf_pages = pdf_document.pages.filter(
            extraction__isnull=False
        ).order_by('page_number')
        
        if not pdf_pages.exists():
            return Response(
                {
                    'success': False,
                    'error': 'No extracted pages found. Run extract_layout first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Settings
        include_skus = request.data.get('include_sku_labels', True)
        
        # Generate previews
        renderer = Gemini3DPreviewRenderer()
        results = []
        generated_count = 0
        skipped_count = 0
        failed_count = 0
        total_start_time = time.time()
        
        for pdf_page in pdf_pages:
            extraction = pdf_page.extraction
            view_type = extraction.structured_data.get('view_type', 'elevation')
            
            # Skip floor plans
            if view_type.lower() == 'plan':
                logger.info(f"⏭️ Skipping floor plan on page {pdf_page.page_number}")
                results.append({
                    'page_number': pdf_page.page_number,
                    'success': False,
                    'reason': 'Floor plan - skipped'
                })
                skipped_count += 1
                continue
            
            # Get SKU matches
            sku_matches = None
            if include_skus:
                sku_matches = list(extraction.sku_matches.all())
            
            # Generate preview
            logger.info(f"📄 Generating 3D preview for page {pdf_page.page_number}")
            result = renderer.generate_3d_preview(
                pdf_page=pdf_page,
                extraction=extraction,
                sku_matches=sku_matches
            )
            
            if result['success']:
                image_url = request.build_absolute_uri(result['image_path'])
                results.append({
                    'page_number': pdf_page.page_number,
                    'success': True,
                    'image_url': image_url,
                    'generation_time': result['generation_time']
                })
                generated_count += 1
            else:
                results.append({
                    'page_number': pdf_page.page_number,
                    'success': False,
                    'error': result.get('error', 'Unknown error')
                })
                failed_count += 1
        
        total_time = time.time() - total_start_time
        
        logger.info(f"✅ Batch 3D preview complete: {generated_count} generated, {skipped_count} skipped, {failed_count} failed")
        
        return Response({
            'success': True,
            'total_pages': pdf_pages.count(),
            'generated': generated_count,
            'skipped': skipped_count,
            'failed': failed_count,
            'results': results,
            'total_time': round(total_time, 2)
        }, status=status.HTTP_200_OK)
    
    except Project.DoesNotExist:
        return Response(
            {
                'success': False,
                'error': 'Project not found or access denied'
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        logger.error(f"Error in batch 3D preview generation: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return Response(
            {
                'success': False,
                'error': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_3d_preview(request, project_id, page_number):
    """
    GET /api/projects/{project_id}/pages/{page_number}/3d_preview/
    
    Retrieve existing 3D preview for a page
    
    Response:
        {
            "exists": true,
            "page_number": 2,
            "image_url": "http://.../media/3d_previews/...",
            "created_at": "2025-10-30T12:00:00Z"
        }
    
    OR:
        {
            "exists": false,
            "page_number": 2,
            "message": "No 3D preview generated yet"
        }
    """
    try:
        # Get project and verify ownership
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Get page
        try:
            pdf_page = project.pdf_document.pages.get(page_number=page_number)
        except PDFPage.DoesNotExist:
            return Response(
                {'error': f'Page {page_number} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if 3D preview exists
        if pdf_page.preview_3d_image:
            image_url = request.build_absolute_uri(pdf_page.preview_3d_image.url)
            
            return Response({
                'exists': True,
                'page_number': page_number,
                'image_url': image_url,
                'created_at': pdf_page.created_at.isoformat()
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'exists': False,
                'page_number': page_number,
                'message': 'No 3D preview generated yet'
            }, status=status.HTTP_200_OK)
    
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        logger.error(f"Error retrieving 3D preview: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )