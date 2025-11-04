# design_agent/tasks.py - UPDATED with detailed logging

import logging
import json
from celery import shared_task
from django.conf import settings

from .models import PDFDocument, PDFPage, Extraction
from .services.pdf_parser import PDFParser
from .services.unified_extractor import UnifiedExtractor
from .services.sku_matcher import SKUMatcher
from .services.gemini_renderer import GeminiRenderer

logger = logging.getLogger('design_agent')


@shared_task
def extract_page_layout(pdf_page_id: str):
    """
    Stage 2: Extract layout from single page
    ENHANCED with detailed debug logging
    """
    try:
        pdf_page = PDFPage.objects.get(id=pdf_page_id)
        
        logger.info(f"📸 Extracting page {pdf_page.page_number} with unified extractor...")
        logger.info(f"   Image path: {pdf_page.image_file.path}")
        
        # Use unified extractor
        extractor = UnifiedExtractor()
        result = extractor.extract_from_image(pdf_page.image_file.path)
        
        # ✅ LOG RAW RESPONSE for debugging
        logger.info("="*70)
        logger.info(f"📋 RAW EXTRACTION RESPONSE (Page {pdf_page.page_number}):")
        logger.info("="*70)
        logger.info(f"Service: {result['service']}")
        logger.info(f"\nRaw Response Preview (first 1000 chars):")
        logger.info(result['raw_response'][:1000])
        logger.info("="*70)
        
        # Parse structured data
        structured_data = result['structured_data']
        
        # ✅ LOG STRUCTURED DATA
        logger.info(f"\n📊 STRUCTURED DATA (Page {pdf_page.page_number}):")
        logger.info(f"   View Type: {structured_data.get('view_type')}")
        logger.info(f"   Total SKUs Claimed: {structured_data.get('total_skus', 'N/A')}")
        logger.info(f"   Items Array Length: {len(structured_data.get('items', []))}")
        
        # ✅ LOG EACH EXTRACTED ITEM
        items = structured_data.get('items', [])
        if items:
            logger.info(f"\n   📦 EXTRACTED ITEMS:")
            for i, item in enumerate(items, 1):
                label = item.get('label', 'NO LABEL')
                category = item.get('category', 'NO CATEGORY')
                dims = item.get('dimensions', {})
                logger.info(f"   {i}. {label} ({category}) - W:{dims.get('width')}, H:{dims.get('height')}, D:{dims.get('depth')}")
        else:
            logger.warning(f"   ⚠️ NO ITEMS EXTRACTED!")
        
        logger.info("="*70)
        
        # Create Extraction record
        extraction = Extraction.objects.create(
            pdf_page=pdf_page,
            structured_data=structured_data,
            extraction_method=result['service'],
            raw_response=result['raw_response'],
            status='completed'
        )
        
        items_count = len(items)
        logger.info(f"✅ Extracted {items_count} items from page {pdf_page.page_number} using {result['service']}")
        
        # ✅ VALIDATION WARNING
        if items_count < 10:
            logger.warning(f"⚠️ LOW EXTRACTION COUNT: Only {items_count} items found (typical: 15-25 per page)")
            logger.warning(f"   This may indicate extraction quality issues")
        
        return {
            'extraction_id': str(extraction.id),
            'items_found': items_count,
            'service_used': result['service']
        }
        
    except Exception as e:
        logger.error(f"❌ Extraction failed for page {pdf_page_id}: {e}")
        logger.error(f"   Exception type: {type(e).__name__}")
        logger.error(f"   Exception details: {str(e)}")
        
        # Create failed extraction record
        Extraction.objects.create(
            pdf_page=pdf_page,
            status='failed',
            raw_response=str(e)
        )
        raise


@shared_task
def process_pdf_to_images(pdf_document_id: str):
    """Stage 1: Convert PDF to images"""
    try:
        pdf_document = PDFDocument.objects.get(id=pdf_document_id)
        parser = PDFParser()
        
        # Convert PDF to images
        pdf_pages = parser.convert_pdf_to_images(pdf_document)
        
        # Update status
        pdf_document.processing_status = 'completed'
        pdf_document.save()
        
        logger.info(f"✅ PDF {pdf_document_id} converted to {len(pdf_pages)} images")
        return {
            'status': 'completed',
            'pages': len(pdf_pages)
        }
        
    except Exception as e:
        logger.error(f"❌ PDF conversion failed: {e}")
        pdf_document.processing_status = 'failed'
        pdf_document.error_message = str(e)
        pdf_document.save()
        raise


@shared_task
def extract_all_pages_for_pdf(pdf_document_id: str):
    """Stage 2: Queue extraction for all pages in PDF"""
    try:
        pdf_document = PDFDocument.objects.get(id=pdf_document_id)
        pages = pdf_document.pages.all().order_by('page_number')
        
        logger.info(f"📋 Queueing extraction for {pages.count()} pages...")
        
        # Queue extraction for each page
        results = []
        for page in pages:
            result = extract_page_layout.delay(str(page.id))
            results.append(result.id)
        
        return {
            'status': 'queued',
            'pages_queued': pages.count(),
            'task_ids': results
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to queue extractions: {e}")
        raise


@shared_task
def match_skus_for_extraction(extraction_id: str):
    """Stage 3: Match SKUs for a single extraction"""
    try:
        extraction = Extraction.objects.get(id=extraction_id)
        
        logger.info(f"🔗 Matching SKUs for extraction {extraction_id}...")
        
        # Use SKU matcher with code-first strategy
        matcher = SKUMatcher(dimension_tolerance=5.0)
        matches = matcher.match_extraction(extraction)
        
        logger.info(f"✅ Matched {len(matches)} SKUs for extraction {extraction_id}")
        
        return {
            'extraction_id': str(extraction_id),
            'matches_found': len(matches)
        }
        
    except Exception as e:
        logger.error(f"❌ SKU matching failed: {e}")
        raise


@shared_task
def generate_all_renders_for_project(project_id: str, style_preference: str = 'modern'):
    """Stage 6: Generate renders for all pages in project"""
    try:
        from .models import Project
        
        project = Project.objects.get(id=project_id)
        
        logger.info(f"🎨 Generating renders for project {project_id} with style: {style_preference}")
        
        renderer = GeminiRenderer()
        renders = renderer.render_all_pages(project, style_preference)
        
        logger.info(f"✅ Generated {len(renders)} renders for project {project_id}")
        
        return {
            'project_id': str(project_id),
            'renders_generated': len(renders),
            'style': style_preference
        }
        
    except Exception as e:
        logger.error(f"❌ Render generation failed: {e}")
        raise
    
# Add this to design_agent/tasks.py

@shared_task(bind=True, max_retries=3)
def regenerate_single_render(self, project_id: str, pdf_page_id: str, style: str, version: int, reason: str):
    """
    Regenerate a single render (used for SKU changes or style updates)
    
    Args:
        project_id: Project UUID
        pdf_page_id: PDFPage UUID
        style: Design style preference
        version: New version number
        reason: Reason for regeneration
    """
    from .models import Project, PDFPage, Extraction, SKUMatch, Render
    from .services.gemini_renderer import GeminiRenderer
    
    logger.info(f"🔄 Task: Regenerating render for page {pdf_page_id} (version {version})")
    
    try:
        project = Project.objects.get(id=project_id)
        pdf_page = PDFPage.objects.get(id=pdf_page_id)
        
        # Get extraction
        if not hasattr(pdf_page, 'extraction'):
            raise ValueError(f"No extraction found for page {pdf_page.page_number}")
        
        extraction = pdf_page.extraction
        
        # Get current SKU matches
        sku_matches = list(extraction.sku_matches.all())
        
        # Initialize renderer
        renderer = GeminiRenderer()
        
        # Generate new render
        new_render = renderer.render_page(
            pdf_page=pdf_page,
            extraction=extraction,
            sku_matches=sku_matches,
            style_preference=style
        )
        
        # Update version and reason
        new_render.version = version
        new_render.is_active = True
        new_render.save()
        
        logger.info(f"✅ Render regenerated successfully: version {version}")
        
        return {
            'status': 'success',
            'render_id': str(new_render.id),
            'version': version,
            'page': pdf_page.page_number
        }
        
    except Exception as e:
        logger.error(f"❌ Render regeneration failed: {str(e)}")
        
        # Mark task as failed
        self.retry(exc=e, countdown=60)  # Retry after 60 seconds
        
        raise