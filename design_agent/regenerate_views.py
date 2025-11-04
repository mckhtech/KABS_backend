# design_agent/regenerate_views.py
"""
Render Regeneration & SKU Replacement APIs
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, Render, SKUMatch, SKUCatalog, PDFPage
from .tasks import regenerate_single_render

logger = logging.getLogger('design_agent')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def regenerate_render(request, project_id, render_id):
    """
    POST /api/projects/{id}/renders/{render_id}/regenerate/
    
    Regenerate a single render with new style or after SKU changes
    
    Request:
        {
            "style": "traditional",  // optional - change style
            "reason": "client requested darker finish"  // optional - for tracking
        }
    
    Response:
        {
            "render_id": "uuid",
            "old_version": 1,
            "new_version": 2,
            "status": "queued",
            "task_id": "celery-task-id",
            "message": "Render regeneration queued"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        render = Render.objects.get(id=render_id, project=project)
        
        # Check if pricing is locked (prevents regeneration)
        if hasattr(project, 'pricing') and project.pricing.status == 'locked':
            return Response(
                {'error': 'Cannot regenerate render - pricing is locked. Unlock pricing first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get new style (or keep existing)
        new_style = request.data.get('style', render.style_preference)
        
        if new_style not in ['modern', 'traditional', 'minimalist']:
            return Response(
                {'error': 'Invalid style. Must be: modern, traditional, or minimalist'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Archive old render (mark as inactive but keep for history)
        render.is_active = False
        render.save()
        
        old_version = render.version
        reason = request.data.get('reason', 'Style change or SKU update')
        
        # Queue regeneration task
        task = regenerate_single_render.delay(
            str(project.id),
            str(render.pdf_page.id),
            new_style,
            old_version + 1,
            reason
        )
        
        logger.info(f"🔄 Queued render regeneration for page {render.pdf_page.page_number}: task {task.id}")
        
        return Response({
            'render_id': str(render.id),
            'old_version': old_version,
            'new_version': old_version + 1,
            'page': render.pdf_page.page_number,
            'new_style': new_style,
            'status': 'queued',
            'task_id': task.id,
            'reason': reason,
            'message': 'Render regeneration queued successfully'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Render.DoesNotExist:
        return Response({'error': 'Render not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error regenerating render: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def replace_sku(request, project_id):
    """
    POST /api/projects/{id}/skus/replace/
    
    Replace a matched SKU and optionally trigger re-render
    
    Request:
        {
            "page_number": 2,
            "old_sku_code": "W361824",
            "new_sku_code": "W362430",
            "regenerate_render": true,  // optional - trigger re-render
            "reason": "Client wants larger cabinet"  // optional
        }
    
    Response:
        {
            "old_sku": {...},
            "new_sku": {...},
            "updated_pages": [2],
            "render_regeneration": {
                "status": "queued",
                "task_id": "..."
            }
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check if pricing is locked
        if hasattr(project, 'pricing') and project.pricing.status == 'locked':
            return Response(
                {'error': 'Cannot replace SKU - pricing is locked. Unlock pricing first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate inputs
        page_number = request.data.get('page_number')
        old_sku_code = request.data.get('old_sku_code')
        new_sku_code = request.data.get('new_sku_code')
        
        if not all([page_number, old_sku_code, new_sku_code]):
            return Response(
                {'error': 'page_number, old_sku_code, and new_sku_code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the page
        pdf_page = PDFPage.objects.get(
            pdf_document=project.pdf_document,
            page_number=page_number
        )
        
        # Get new SKU from catalog
        new_sku = SKUCatalog.objects.get(code=new_sku_code, is_active=True)
        
        # Find and update SKU match
        sku_match = SKUMatch.objects.get(
            extraction__pdf_page=pdf_page,
            matched_sku__code=old_sku_code
        )
        
        old_sku = sku_match.matched_sku
        
        # Update the match
        sku_match.matched_sku = new_sku
        sku_match.match_score = 1.0  # Manual replacement = perfect match
        sku_match.save()
        
        logger.info(f"🔄 Replaced SKU {old_sku_code} → {new_sku_code} on page {page_number}")
        
        response_data = {
            'old_sku': {
                'code': old_sku.code,
                'name': old_sku.name
            },
            'new_sku': {
                'code': new_sku.code,
                'name': new_sku.name,
                'price': str(new_sku.price) if new_sku.price else None,
                'dimensions': {
                    'width': float(new_sku.width) if new_sku.width else None,
                    'height': float(new_sku.height) if new_sku.height else None,
                    'depth': float(new_sku.depth) if new_sku.depth else None
                }
            },
            'updated_pages': [page_number],
            'message': f'SKU replaced successfully on page {page_number}'
        }
        
        # Optionally regenerate render
        regenerate = request.data.get('regenerate_render', True)
        
        if regenerate:
            # Find active render for this page
            render = Render.objects.filter(
                project=project,
                pdf_page=pdf_page,
                is_active=True
            ).first()
            
            if render:
                # Archive old render
                render.is_active = False
                render.save()
                
                # Queue regeneration
                reason = request.data.get('reason', f'SKU replacement: {old_sku_code} → {new_sku_code}')
                task = regenerate_single_render.delay(
                    str(project.id),
                    str(pdf_page.id),
                    render.style_preference,
                    render.version + 1,
                    reason
                )
                
                response_data['render_regeneration'] = {
                    'status': 'queued',
                    'task_id': task.id,
                    'page': page_number
                }
                
                logger.info(f"🎨 Queued render regeneration after SKU replacement: task {task.id}")
        
        # Update pricing if exists
        if hasattr(project, 'pricing'):
            pricing = project.pricing
            pricing.calculate_totals()
            pricing.save()
            
            response_data['pricing_updated'] = True
            response_data['new_total'] = str(pricing.total)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except PDFPage.DoesNotExist:
        return Response({'error': f'Page {page_number} not found'}, status=status.HTTP_404_NOT_FOUND)
    except SKUCatalog.DoesNotExist:
        return Response({'error': f'SKU {new_sku_code} not found in catalog'}, status=status.HTTP_404_NOT_FOUND)
    except SKUMatch.DoesNotExist:
        return Response({'error': f'SKU match for {old_sku_code} on page {page_number} not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error replacing SKU: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def render_history(request, project_id, page_number):
    """
    GET /api/projects/{id}/renders/history/?page={page_number}
    
    Get all render versions for a specific page
    
    Response:
        {
            "page": 2,
            "total_versions": 3,
            "active_version": 3,
            "renders": [
                {
                    "render_id": "uuid",
                    "version": 3,
                    "status": "completed",
                    "style": "modern",
                    "image_url": "...",
                    "created_at": "...",
                    "is_active": true,
                    "reason": "SKU replacement"
                },
                {
                    "render_id": "uuid",
                    "version": 2,
                    "status": "completed",
                    "style": "traditional",
                    "image_url": "...",
                    "created_at": "...",
                    "is_active": false,
                    "reason": "Style change"
                }
            ]
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Get page
        pdf_page = PDFPage.objects.get(
            pdf_document=project.pdf_document,
            page_number=page_number
        )
        
        # Get all renders for this page (including archived)
        renders = Render.objects.filter(
            project=project,
            pdf_page=pdf_page
        ).order_by('-version')
        
        if not renders.exists():
            return Response(
                {'error': f'No renders found for page {page_number}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        active_render = renders.filter(is_active=True).first()
        
        response_data = {
            'page': page_number,
            'total_versions': renders.count(),
            'active_version': active_render.version if active_render else None,
            'renders': []
        }
        
        for render in renders:
            render_data = {
                'render_id': str(render.id),
                'version': render.version,
                'status': render.status,
                'style': render.style_preference,
                'created_at': render.created_at,
                'is_active': render.is_active,
                'generation_time': render.generation_time
            }
            
            if render.status == 'completed' and render.image_file:
                render_data['image_url'] = request.build_absolute_uri(render.image_file.url)
            
            if render.status == 'failed':
                render_data['error'] = render.error_message
            
            response_data['renders'].append(render_data)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except PDFPage.DoesNotExist:
        return Response({'error': f'Page {page_number} not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching render history: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)