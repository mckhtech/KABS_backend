# design_agent/annotation_views.py
"""
Annotation Management APIs
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, Render, Annotation

logger = logging.getLogger('design_agent')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_annotation(request, project_id):
    """
    POST /api/projects/{id}/annotations/
    
    Create annotation for a render
    
    Request:
        {
            "render_id": "uuid",
            "annotation_type": "special_cabinet",  // special_cabinet, comment, change_request
            "text": "Please use premium hardware for this cabinet",
            "sku_code": "W2130-15L",  // optional
            "position_x": 100,  // optional
            "position_y": 200   // optional
        }
    
    Response:
        {
            "annotation_id": "uuid",
            "message": "Annotation created successfully"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Validate inputs
        render_id = request.data.get('render_id')
        annotation_type = request.data.get('annotation_type')
        text = request.data.get('text')
        
        if not render_id or not annotation_type or not text:
            return Response(
                {'error': 'render_id, annotation_type, and text are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if annotation_type not in ['special_cabinet', 'comment', 'change_request']:
            return Response(
                {'error': 'Invalid annotation_type. Must be: special_cabinet, comment, or change_request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get render
        render = Render.objects.get(id=render_id, project=project)
        
        # Create annotation
        annotation = Annotation.objects.create(
            render=render,
            annotation_type=annotation_type,
            text=text,
            sku_code=request.data.get('sku_code'),
            position_x=request.data.get('position_x'),
            position_y=request.data.get('position_y'),
            created_by=request.user
        )
        
        logger.info(f"Created annotation {annotation.id} for project {project_id}")
        
        return Response({
            'annotation_id': str(annotation.id),
            'annotation_type': annotation.annotation_type,
            'text': annotation.text,
            'render_id': str(render.id),
            'created_at': annotation.created_at,
            'message': 'Annotation created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Render.DoesNotExist:
        return Response({'error': 'Render not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error creating annotation: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_annotations(request, project_id):
    """
    GET /api/projects/{id}/annotations/
    
    List all annotations for a project
    
    Response:
        {
            "project_id": "uuid",
            "total_annotations": 5,
            "annotations": [
                {
                    "id": "uuid",
                    "render_id": "uuid",
                    "page": 1,
                    "annotation_type": "special_cabinet",
                    "text": "...",
                    "sku_code": "W2130-15L",
                    "created_at": "2025-10-27T10:30:00Z"
                }
            ]
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        annotations = Annotation.objects.filter(
            render__project=project
        ).select_related('render', 'render__pdf_page')
        
        annotations_data = []
        for annotation in annotations:
            annotations_data.append({
                'id': str(annotation.id),
                'render_id': str(annotation.render.id),
                'page': annotation.render.pdf_page.page_number,
                'annotation_type': annotation.annotation_type,
                'text': annotation.text,
                'sku_code': annotation.sku_code,
                'position': {
                    'x': annotation.position_x,
                    'y': annotation.position_y
                } if annotation.position_x else None,
                'created_by': annotation.created_by.username,
                'created_at': annotation.created_at
            })
        
        return Response({
            'project_id': str(project.id),
            'total_annotations': len(annotations_data),
            'annotations': annotations_data
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error listing annotations: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_annotation(request, project_id, annotation_id):
    """
    DELETE /api/projects/{id}/annotations/{annotation_id}/
    
    Delete an annotation
    
    Response:
        {
            "message": "Annotation deleted successfully"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        annotation = Annotation.objects.get(id=annotation_id, render__project=project)
        
        annotation.delete()
        
        logger.info(f"Deleted annotation {annotation_id} from project {project_id}")
        
        return Response({
            'message': 'Annotation deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Annotation.DoesNotExist:
        return Response({'error': 'Annotation not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error deleting annotation: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_annotation(request, project_id, annotation_id):
    """
    PUT /api/projects/{id}/annotations/{annotation_id}/
    
    Update an annotation
    
    Request:
        {
            "text": "Updated annotation text",
            "annotation_type": "comment"  // optional
        }
    
    Response:
        {
            "annotation_id": "uuid",
            "message": "Annotation updated successfully"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        annotation = Annotation.objects.get(id=annotation_id, render__project=project)
        
        # Update fields
        if 'text' in request.data:
            annotation.text = request.data['text']
        
        if 'annotation_type' in request.data:
            if request.data['annotation_type'] not in ['special_cabinet', 'comment', 'change_request']:
                return Response(
                    {'error': 'Invalid annotation_type'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            annotation.annotation_type = request.data['annotation_type']
        
        if 'sku_code' in request.data:
            annotation.sku_code = request.data['sku_code']
        
        annotation.save()
        
        logger.info(f"Updated annotation {annotation_id}")
        
        return Response({
            'annotation_id': str(annotation.id),
            'text': annotation.text,
            'annotation_type': annotation.annotation_type,
            'message': 'Annotation updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Annotation.DoesNotExist:
        return Response({'error': 'Annotation not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating annotation: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)