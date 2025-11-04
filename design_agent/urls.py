# design_agent/urls.py
"""
Complete URL routing for Design Agent API - FINAL VERSION
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, auth_views, pricing_views, annotation_views, approval_views
from .regenerate_views import regenerate_render, replace_sku, render_history
from .edit_views import load_project_for_editing, update_project_metadata, duplicate_project
from .preview_3d_views import (
    generate_3d_preview,
    batch_generate_3d_previews,
    get_3d_preview
)
# Create router for ViewSets
router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')

urlpatterns = [
path('auth/register/', auth_views.register, name='auth-register'),
    path('auth/login/', auth_views.login, name='auth-login'),
    path('auth/logout/', auth_views.logout, name='auth-logout'),
    path('auth/profile/', auth_views.profile, name='auth-profile'),

    # - GET    /api/projects/                        -> List projects
    # - POST   /api/projects/                        -> Create project
    # - GET    /api/projects/{id}/                   -> Get project details
    # - PUT    /api/projects/{id}/                   -> Update project
    # - DELETE /api/projects/{id}/                   -> Delete project
    # - GET    /api/projects/{id}/status/            -> Project status
    # - GET    /api/projects/{id}/summary/           -> Complete summary
    # - POST   /api/projects/{id}/upload_pdf/        -> Upload PDF
    # - GET    /api/projects/{id}/files/             -> Get PDF files
    # - POST   /api/projects/{id}/extract_layout/    -> Extract layout
    # - GET    /api/projects/{id}/extraction_results/ -> Get extractions
    # - POST   /api/projects/{id}/match_skus/        -> Match SKUs
    # - GET    /api/projects/{id}/validate_skus/     -> Validate SKU images
    # - POST   /api/projects/{id}/generate_renders/  -> Generate renders
    # - GET    /api/projects/{id}/renders/           -> Get renders
    # - GET    /api/projects/{id}/download_report/   -> Download final PDF
    path('', include(router.urls)),
    
    path('projects/<uuid:project_id>/pricing/generate/', 
         pricing_views.generate_pricing, 
         name='generate_pricing'),
    
    path('projects/<uuid:project_id>/pricing/', 
         pricing_views.get_pricing, 
         name='get_pricing'),
    
     path('projects/<uuid:project_id>/pricing/items/<int:item_id>/', 
          pricing_views.update_pricing_item, name='update_pricing_item'),

     path('projects/<uuid:project_id>/pricing/items/<int:item_id>/delete/', 
          pricing_views.delete_pricing_item, name='delete_pricing_item'), 
     
     path('projects/<uuid:project_id>/pricing/items/', 
          pricing_views.add_custom_item, 
          name='add_custom_item'),
     
    path('projects/<uuid:project_id>/pricing/update/', 
         pricing_views.update_project_pricing, 
         name='update_project_pricing'),
    
    path('projects/<uuid:project_id>/pricing/lock/', 
         pricing_views.lock_pricing, 
         name='lock_pricing'),
    
    path('projects/<uuid:project_id>/pricing/unlock/', 
         pricing_views.unlock_pricing, 
         name='unlock_pricing'),
    
    path('projects/<uuid:project_id>/annotations/', 
         annotation_views.list_annotations, 
         name='list_annotations'),
    
    path('projects/<uuid:project_id>/annotations/create/', 
         annotation_views.create_annotation, 
         name='create_annotation'),
    
    path('projects/<uuid:project_id>/annotations/<uuid:annotation_id>/', 
         annotation_views.update_annotation, 
         name='update_annotation'),
    
    path('projects/<uuid:project_id>/annotations/<uuid:annotation_id>/delete/', 
         annotation_views.delete_annotation, 
         name='delete_annotation'),
    
     path('projects/<uuid:project_id>/approve/', 
         approval_views.approve_project, 
         name='approve_project'),
    
    path('projects/<uuid:project_id>/unapprove/', 
         approval_views.unapprove_project, 
         name='unapprove_project'),
    
    path('projects/<uuid:project_id>/approval/', 
         approval_views.approval_status, 
         name='approval_status'),
    
    path('projects/<uuid:project_id>/renders/<uuid:render_id>/regenerate/', 
         regenerate_render, 
         name='regenerate_render'),
    
    path('projects/<uuid:project_id>/renders/history/', 
         render_history, 
         name='render_history'),
    
    path('projects/<uuid:project_id>/skus/replace/', 
         replace_sku, 
         name='replace_sku'),
    
    path('projects/<uuid:project_id>/edit/', 
         load_project_for_editing, 
         name='load_project_edit'),
    
    path('projects/<uuid:project_id>/metadata/', 
         update_project_metadata, 
         name='update_project_metadata'),
    
    path('projects/<uuid:project_id>/duplicate/', 
         duplicate_project, 
         name='duplicate_project'),
    
    
    # 3D Preview Generation (Testing)
     path('projects/<uuid:project_id>/pages/<int:page_number>/generate_3d_preview/',
          generate_3d_preview,
          name='generate_3d_preview'),

     path('projects/<uuid:project_id>/generate_all_3d_previews/',
          batch_generate_3d_previews,
          name='batch_generate_3d_previews'),

     path('projects/<uuid:project_id>/pages/<int:page_number>/3d_preview/',
          get_3d_preview,
          name='get_3d_preview'),
]