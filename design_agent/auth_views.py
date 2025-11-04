# design_agent/auth_views.py
"""
Simple token-based authentication
Uses Django REST Framework's built-in token auth
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.contrib.auth import authenticate

from .models import Project
from .serializers import ProjectSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    POST /api/auth/register/
    
    Create new user account
    
    Request:
        {
            "username": "architect123",
            "email": "user@example.com",
            "password": "securepass123",
            "first_name": "John",  // optional
            "last_name": "Doe"     // optional
        }
    
    Response:
        {
            "user_id": 1,
            "username": "architect123",
            "email": "user@example.com",
            "token": "abc123...",
            "message": "User created successfully"
        }
    """
    # Validate required fields
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Username and password are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if username exists
    if User.objects.filter(username=username).exists():
        return Response(
            {'error': 'Username already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if email exists (if provided)
    if email and User.objects.filter(email=email).exists():
        return Response(
            {'error': 'Email already registered'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email or '',
            password=password,
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', '')
        )
        
        # Generate token
        token, _ = Token.objects.get_or_create(user=user)
        
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'token': token.key,
            'message': 'User created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    POST /api/auth/login/
    
    Login and get authentication token
    
    Request:
        {
            "username": "architect123",
            "password": "securepass123"
        }
    
    Response:
        {
            "token": "abc123...",
            "user_id": 1,
            "username": "architect123",
            "email": "user@example.com"
        }
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Username and password are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Authenticate user
    user = authenticate(username=username, password=password)
    
    if user is None:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not user.is_active:
        return Response(
            {'error': 'Account is disabled'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get or create token
    token, _ = Token.objects.get_or_create(user=user)
    
    return Response({
        'token': token.key,
        'user_id': user.id,
        'username': user.username,
        'email': user.email
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    POST /api/auth/logout/
    
    Logout and delete token
    Requires: Authorization header with token
    
    Response:
        {"message": "Logged out successfully"}
    """
    try:
        # Delete the user's token
        request.user.auth_token.delete()
        return Response(
            {'message': 'Logged out successfully'},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    GET /api/auth/profile/
    
    Get current user info and their projects
    Requires: Authorization header with token
    
    Response:
        {
            "user": {
                "id": 1,
                "username": "architect123",
                "email": "user@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "date_joined": "2025-01-15T10:30:00Z"
            },
            "projects": [
                {
                    "id": "uuid-123",
                    "name": "Kitchen Renovation",
                    "project_type": "kitchen",
                    "created_at": "2025-01-20T14:00:00Z"
                }
            ],
            "stats": {
                "total_projects": 5,
                "completed_renders": 12
            }
        }
    """
    user = request.user
    
    # Get user's projects
    projects = Project.objects.filter(
        created_by=user,
        is_active=True
    ).order_by('-created_at')
    
    # Calculate stats
    total_projects = projects.count()
    completed_renders = sum(
        project.renders.filter(status='completed').count()
        for project in projects
    )
    
    return Response({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined
        },
        'projects': ProjectSerializer(projects, many=True).data,
        'stats': {
            'total_projects': total_projects,
            'completed_renders': completed_renders
        }
    }, status=status.HTTP_200_OK)