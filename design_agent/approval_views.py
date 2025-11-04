# design_agent/approval_views.py
"""
Project Approval & Locking APIs
"""

import logging
from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, Pricing, Render

logger = logging.getLogger('design_agent')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_project(request, project_id):
    """
    POST /api/projects/{id}/approve/
    
    Approve project - locks pricing, renders, and enables PDF export
    
    Request:
        {
            "notes": "Client approved design on call"  // optional
        }
    
    Response:
        {
            "project_id": "uuid",
            "status": "approved",
            "approved_at": "2025-10-27T10:30:00Z",
            "locked_items": {
                "pricing": true,
                "renders": 3
            },
            "message": "Project approved and locked successfully"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check if already approved
        if project.is_approved:
            return Response(
                {'error': 'Project is already approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate project is ready for approval
        validation_errors = []
        
        # Must have pricing
        if not hasattr(project, 'pricing'):
            validation_errors.append('No pricing generated')
        
        # Must have at least one completed render
        completed_renders = Render.objects.filter(
            project=project,
            status='completed',
            is_active=True
        )
        if not completed_renders.exists():
            validation_errors.append('No completed renders')
        
        if validation_errors:
            return Response(
                {
                    'error': 'Project not ready for approval',
                    'validation_errors': validation_errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Lock pricing
        pricing = project.pricing
        if pricing.status != 'locked':
            pricing.status = 'locked'
            pricing.save()
            logger.info(f"🔒 Locked pricing for project {project_id}")
        
        # Mark project as approved
        project.is_approved = True
        project.approved_at = datetime.now()
        project.approved_by = request.user
        
        if 'notes' in request.data:
            project.notes = request.data['notes']
        
        project.save()
        
        logger.info(f"✅ Project {project_id} approved by {request.user.username}")
        
        return Response({
            'project_id': str(project.id),
            'status': 'approved',
            'approved_at': project.approved_at,
            'approved_by': request.user.username,
            'locked_items': {
                'pricing': True,
                'renders': completed_renders.count()
            },
            'message': 'Project approved and locked successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error approving project: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unapprove_project(request, project_id):
    """
    POST /api/projects/{id}/unapprove/
    
    Unapprove project - unlocks for editing
    
    Response:
        {
            "project_id": "uuid",
            "status": "draft",
            "message": "Project unlocked for editing"
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        if not project.is_approved:
            return Response(
                {'error': 'Project is not approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Unlock project
        project.is_approved = False
        project.approved_at = None
        project.approved_by = None
        project.save()
        
        # Unlock pricing
        if hasattr(project, 'pricing'):
            pricing = project.pricing
            pricing.status = 'draft'
            pricing.save()
        
        logger.info(f"🔓 Project {project_id} unlocked by {request.user.username}")
        
        return Response({
            'project_id': str(project.id),
            'status': 'draft',
            'message': 'Project unlocked for editing'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error unapproving project: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def approval_status(request, project_id):
    """
    GET /api/projects/{id}/approval/
    
    Get project approval status
    
    Response:
        {
            "project_id": "uuid",
            "is_approved": true,
            "approved_at": "2025-10-27T10:30:00Z",
            "approved_by": "john_doe",
            "can_approve": true,
            "validation": {
                "has_pricing": true,
                "has_renders": true,
                "pricing_locked": true,
                "errors": []
            }
        }
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        
        # Check approval readiness
        has_pricing = hasattr(project, 'pricing')
        has_renders = Render.objects.filter(
            project=project,
            status='completed',
            is_active=True
        ).exists()
        
        validation_errors = []
        if not has_pricing:
            validation_errors.append('No pricing generated')
        if not has_renders:
            validation_errors.append('No completed renders')
        
        pricing_locked = False
        if has_pricing:
            pricing_locked = project.pricing.status == 'locked'
        
        can_approve = len(validation_errors) == 0 and not project.is_approved
        
        return Response({
            'project_id': str(project.id),
            'is_approved': project.is_approved,
            'approved_at': project.approved_at,
            'approved_by': project.approved_by.username if project.approved_by else None,
            'can_approve': can_approve,
            'validation': {
                'has_pricing': has_pricing,
                'has_renders': has_renders,
                'pricing_locked': pricing_locked,
                'errors': validation_errors
            }
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error checking approval status: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)