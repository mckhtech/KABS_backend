# design_agent/edit_views.py
"""
Edit & Load Existing Projects
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, Render, SKUMatch

logger = logging.getLogger('design_agent')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def load_project_for_editing(request, project_id):
    """
    GET /api/projects/{id}/edit/
    
    Load complete project data for editing
    
    Response:
        {
            "project": {...},
            "pdf_document": {...},
            "pages": [
                {
                    "page_number": 1,
                    "extraction": {...},
                    "sku_matches": [...],
                    "renders": [...]
                }
            ],
            "pricing": {...},
            "annotations": [...]
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        response_data = {
            'project': {
                'id': str(project.id),
                'name': project.name,
                'project_type': project.project_type,
                'is_approved': project.is_approved,
                'created_at': project.created_at,
                'updated_at': project.updated_at
            }
        }
        
        # PDF Document
        if hasattr(project, 'pdf_document'):
            pdf_doc = project.pdf_document
            response_data['pdf_document'] = {
                'id': str(pdf_doc.id),
                'filename': pdf_doc.filename,
                'page_count': pdf_doc.page_count,
                'processing_status': pdf_doc.processing_status
            }
            
            # Pages with extractions, SKU matches, and renders
            pages_data = []
            
            for page in pdf_doc.pages.all().order_by('page_number'):
                page_data = {
                    'page_number': page.page_number,
                    'image_url': request.build_absolute_uri(page.image_file.url) if page.image_file else None
                }
                
                # Extraction
                if hasattr(page, 'extraction'):
                    extraction = page.extraction
                    page_data['extraction'] = {
                        'id': str(extraction.id),
                        'status': extraction.status,
                        'view_type': extraction.structured_data.get('view_type'),
                        'items_count': len(extraction.structured_data.get('items', []))
                    }
                    
                    # SKU Matches
                    sku_matches = extraction.sku_matches.select_related('matched_sku').all()
                    page_data['sku_matches'] = [
                        {
                            'id': str(match.id),
                            'label_text': match.label_text,
                            'matched_sku': {
                                'code': match.matched_sku.code,
                                'name': match.matched_sku.name,
                                'price': str(match.matched_sku.price) if match.matched_sku.price else None,
                                'dimensions': {
                                    'width': float(match.matched_sku.width) if match.matched_sku.width else None,
                                    'height': float(match.matched_sku.height) if match.matched_sku.height else None,
                                    'depth': float(match.matched_sku.depth) if match.matched_sku.depth else None
                                },
                                'image_url': request.build_absolute_uri(match.matched_sku.image.url) if match.matched_sku.image else None
                            },
                            'match_score': match.match_score,
                            'alternatives': match.alternative_skus
                        }
                        for match in sku_matches
                    ]
                
                # Renders (including history)
                renders = Render.objects.filter(
                    project=project,
                    pdf_page=page
                ).order_by('-version')
                
                page_data['renders'] = [
                    {
                        'id': str(render.id),
                        'version': render.version,
                        'status': render.status,
                        'style': render.style_preference,
                        'is_active': render.is_active,
                        'image_url': request.build_absolute_uri(render.image_file.url) if render.image_file and render.status == 'completed' else None,
                        'created_at': render.created_at
                    }
                    for render in renders
                ]
                
                pages_data.append(page_data)
            
            response_data['pages'] = pages_data
        
        # Pricing
        if hasattr(project, 'pricing'):
            pricing = project.pricing
            response_data['pricing'] = {
                'id': str(pricing.id),
                'status': pricing.status,
                'subtotal': str(pricing.subtotal),
                'total': str(pricing.total),
                'items': [
                    {
                        'id': str(item.id),
                        'sku_code': item.sku_code,
                        'sku_name': item.sku_name,
                        'quantity': item.quantity,
                        'unit_price': str(item.unit_price),
                        'final_price': str(item.final_price)
                    }
                    for item in project.pricing_items.all()
                ]
            }
        
        # Annotations
        from .models import Annotation
        annotations = Annotation.objects.filter(
            render__project=project
        ).select_related('render__pdf_page')
        
        response_data['annotations'] = [
            {
                'id': str(annotation.id),
                'page': annotation.render.pdf_page.page_number,
                'annotation_type': annotation.annotation_type,
                'text': annotation.text,
                'sku_code': annotation.sku_code,
                'created_by': annotation.created_by.username,
                'created_at': annotation.created_at
            }
            for annotation in annotations
        ]
        
        logger.info(f"✅ Loaded project {project_id} for editing")
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error loading project for editing: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_project_metadata(request, project_id):
    """
    PUT /api/projects/{id}/metadata/
    
    Update project name and type
    
    Request:
        {
            "name": "Updated Kitchen Design",
            "project_type": "kitchen"
        }
    
    Response:
        {
            "project_id": "uuid",
            "name": "Updated Kitchen Design",
            "project_type": "kitchen",
            "message": "Project updated successfully"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check if approved (prevent editing approved projects)
        if project.is_approved:
            return Response(
                {'error': 'Cannot edit approved project. Unapprove first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update fields
        if 'name' in request.data:
            project.name = request.data['name']
        
        if 'project_type' in request.data:
            if request.data['project_type'] not in ['kitchen', 'bathroom']:
                return Response(
                    {'error': 'Invalid project_type. Must be: kitchen or bathroom'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            project.project_type = request.data['project_type']
        
        if 'notes' in request.data:
            project.notes = request.data['notes']
        
        project.save()
        
        logger.info(f"✅ Updated project {project_id} metadata")
        
        return Response({
            'project_id': str(project.id),
            'name': project.name,
            'project_type': project.project_type,
            'notes': project.notes,
            'message': 'Project updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def duplicate_project(request, project_id):
    """
    POST /api/projects/{id}/duplicate/
    
    Create a copy of existing project
    
    Request:
        {
            "new_name": "Kitchen Design - Version 2"  // optional
        }
    
    Response:
        {
            "new_project_id": "uuid",
            "name": "Kitchen Design - Version 2",
            "message": "Project duplicated successfully"
        }
    """
    try:
        original_project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Create new project
        new_name = request.data.get('new_name', f"{original_project.name} (Copy)")
        
        new_project = Project.objects.create(
            name=new_name,
            project_type=original_project.project_type,
            created_by=request.user,
            notes=original_project.notes
        )
        
        logger.info(f"📋 Created duplicate project {new_project.id} from {project_id}")
        
        # Note: PDF, extractions, SKU matches would need to be copied separately
        # For now, just create empty project - user can re-upload PDF
        
        return Response({
            'new_project_id': str(new_project.id),
            'name': new_project.name,
            'project_type': new_project.project_type,
            'message': 'Project duplicated successfully. Upload PDF to continue.'
        }, status=status.HTTP_201_CREATED)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error duplicating project: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)