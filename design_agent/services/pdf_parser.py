"""
PDF Parser Service - OpenAI Vision API
Optimized prompt for accurate dimension extraction
"""

import os
import base64
import logging
import json
from typing import List
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_path
from django.core.files.base import ContentFile
from django.conf import settings
import openai

from design_agent.models import PDFDocument, PDFPage, Extraction

logger = logging.getLogger('design_agent')


class PDFParser:
    """Parse kitchen/bath design PDFs and extract structured data"""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.dpi = getattr(settings, 'PDF_DPI', 300)
    
    def convert_pdf_to_images(self, pdf_document: PDFDocument) -> List[PDFPage]:
        """
        Convert PDF to high-resolution images
        Returns list of PDFPage objects
        """
        logger.info(f"Converting PDF {pdf_document.id} to images at {self.dpi} DPI")
        
        try:
            # Convert PDF to images
            images = convert_from_path(
                pdf_document.file.path,
                dpi=self.dpi,
                fmt='png'
            )
            
            pdf_pages = []
            for page_num, image in enumerate(images, start=1):
                # Save image
                image_io = BytesIO()
                image.save(image_io, format='PNG', optimize=True)
                image_io.seek(0)
                
                # Create PDFPage record
                pdf_page = PDFPage.objects.create(
                    pdf_document=pdf_document,
                    page_number=page_num,
                    width=image.width,
                    height=image.height,
                    dpi=self.dpi
                )
                
                # Save image file
                image_filename = f"page_{page_num}_{pdf_document.id}.png"
                pdf_page.image_file.save(
                    image_filename,
                    ContentFile(image_io.read()),
                    save=True
                )
                
                pdf_pages.append(pdf_page)
                logger.info(f"Created page {page_num} for PDF {pdf_document.id}")
            
            # Update PDF document
            pdf_document.page_count = len(images)
            pdf_document.processing_status = 'converting'
            pdf_document.save()
            
            return pdf_pages
            
        except Exception as e:
            logger.error(f"Error converting PDF {pdf_document.id}: {str(e)}")
            pdf_document.processing_status = 'failed'
            pdf_document.error_message = str(e)
            pdf_document.save()
            raise
    
    def extract_from_page(self, pdf_page: PDFPage) -> Extraction:
        """
        Extract structured data from PDF page using OpenAI Vision
        IMPROVED PROMPT for accurate dimension extraction
        """
        logger.info(f"Extracting data from page {pdf_page.page_number} using OpenAI Vision")
        
        try:
            # Read image and encode to base64
            with pdf_page.image_file.open('rb') as img_file:
                image_data = img_file.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Create optimized extraction prompt
            prompt = self._create_extraction_prompt()
            
            # Call OpenAI Vision API with JSON mode
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # Latest vision model
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert CAD drawing analyst specializing in kitchen and bathroom designs. 
Your task is to extract ALL labels, codes, and dimensions with PERFECT accuracy.
Pay special attention to dimension lines, measurement text, and spatial relationships.
Return ONLY valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                    "detail": "high"  # Critical for dimension accuracy
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4000,
                temperature=0,  # Zero temperature for deterministic output
                response_format={"type": "json_object"}
            )
            
            # Parse response
            raw_response = response.choices[0].message.content
            structured_data = json.loads(raw_response)
            
            # Validate structure
            if not self._validate_extraction(structured_data):
                raise ValueError("Invalid extraction format from OpenAI")
            
            # Create Extraction record
            extraction = Extraction.objects.create(
                pdf_page=pdf_page,
                structured_data=structured_data,
                extraction_method='openai_gpt4o_vision',
                raw_response=raw_response
            )
            
            logger.info(f"Extracted {len(structured_data.get('items', []))} items from page {pdf_page.page_number}")
            return extraction
            
        except Exception as e:
            logger.error(f"Error extracting from page {pdf_page.id}: {str(e)}")
            raise
    
    def _create_extraction_prompt(self) -> str:
        """
        Create detailed prompt for accurate extraction
        This is the KEY to fixing your dimension accuracy issues
        """
        return """Analyze this kitchen/bathroom design drawing and extract information with EXTREME precision.

**CRITICAL INSTRUCTIONS:**

1. **LABELS/CODES**: Extract ALL visible product codes exactly as written:
   - Examples: "BC242484-1TDL", "W2130-15L", "SB42FH", "WP3024-15HK"
   - Include ALL characters including dashes and suffixes (L/R/FH/HK)
   - Location: Usually placed near or inside the item representation

2. **DIMENSIONS**: Look for dimension lines and measurement text:
   - Find dimension lines (lines with arrows/ticks showing measurements)
   - Extract the EXACT number value (e.g., 24", 42 3/8", 67 1/2")
   - Convert fractions to decimals: 3/8" = 0.375", 1/2" = 0.5", 1/4" = 0.25"
   - Match dimensions to their corresponding items by proximity
   - Width is typically horizontal, Height is vertical, Depth is noted separately

3. **POSITION**: Estimate X,Y coordinates:
   - X: horizontal distance from left edge (in inches)
   - Y: vertical distance from top edge (in inches)
   - Use dimension lines and spacing to calculate positions

4. **VIEW TYPE**: Identify the drawing type:
   - "elevation" = front/side view showing vertical layout
   - "plan" = top-down view showing floor layout
   - "island" = standalone island view
   - "detail" = close-up detail view

5. **CATEGORY**: Determine item type from code prefix:
   - BC/SB/DB/B/BTB = "cabinet"
   - W/WP = "wall_cabinet"
   - OV = "oven_cabinet"
   - BI/DISH/CKT = "appliance"
   - FLAT PNL = "panel"
   - USF/FL = "filler"

**OUTPUT FORMAT (STRICT JSON):**

{
  "view_type": "elevation",
  "items": [
    {
      "label": "BC242484-1TDL",
      "category": "cabinet",
      "position": {"x": 0, "y": 120},
      "dimensions": {
        "width": 24.0,
        "height": 84.0,
        "depth": 24.0
      },
      "notes": "Base corner cabinet, tall"
    },
    {
      "label": "W2130-15L",
      "category": "wall_cabinet",
      "position": {"x": 24, "y": 0},
      "dimensions": {
        "width": 21.0,
        "height": 30.0,
        "depth": 15.0
      },
      "notes": "Wall cabinet, left hinge"
    }
  ]
}

**EXAMPLE DIMENSION READING:**
If you see: "42 3/8"" → output: 42.375
If you see: "24"" → output: 24.0
If you see: "67 1/2"" → output: 67.5

Extract EVERY visible label and dimension. Be meticulous."""

    def _validate_extraction(self, data: dict) -> bool:
        """Validate extraction structure"""
        if not isinstance(data, dict):
            return False
        
        if 'view_type' not in data or 'items' not in data:
            return False
        
        if not isinstance(data['items'], list):
            return False
        
        # Validate each item
        for item in data['items']:
            required_fields = ['label', 'category', 'position', 'dimensions']
            if not all(field in item for field in required_fields):
                return False
            
            # Validate position structure
            if not isinstance(item['position'], dict) or \
               'x' not in item['position'] or 'y' not in item['position']:
                return False
            
            # Validate dimensions structure
            if not isinstance(item['dimensions'], dict):
                return False
        
        return True
    
    def extract_all_pages(self, pdf_document: PDFDocument) -> List[Extraction]:
        """
        Complete extraction pipeline:
        1. Convert PDF to images
        2. Extract data from each page
        
        Returns list of Extraction objects (one per page)
        """
        logger.info(f"Starting full extraction for PDF {pdf_document.id}")
        
        # Step 1: Convert to images
        pdf_pages = self.convert_pdf_to_images(pdf_document)
        
        # Step 2: Extract from each page
        extractions = []
        for pdf_page in pdf_pages:
            try:
                extraction = self.extract_from_page(pdf_page)
                extractions.append(extraction)
            except Exception as e:
                logger.error(f"Failed to extract page {pdf_page.page_number}: {str(e)}")
                # Continue with other pages even if one fails
                continue
        
        # Update document status
        if extractions:
            pdf_document.processing_status = 'completed'
            pdf_document.save()
        
        logger.info(f"Completed extraction: {len(extractions)}/{len(pdf_pages)} pages successful")
        return extractions
    
    def extract_page_layout(self, pdf_page: PDFPage) -> dict:
        """
        Extract structured data from PDF page and return just the data dict
        (doesn't create Extraction object - for use with Celery tasks)
        """
        logger.info(f"Extracting data from page {pdf_page.page_number} using OpenAI Vision")
        
        try:
            # Read image and encode to base64
            with pdf_page.image_file.open('rb') as img_file:
                image_data = img_file.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Create optimized extraction prompt
            prompt = self._create_extraction_prompt()
            
            # Call OpenAI Vision API with JSON mode
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert CAD drawing analyst specializing in kitchen and bathroom designs. 
    Your task is to extract ALL labels, codes, and dimensions with PERFECT accuracy.
    Pay special attention to dimension lines, measurement text, and spatial relationships.
    Return ONLY valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4000,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            raw_response = response.choices[0].message.content
            structured_data = json.loads(raw_response)
            
            # Validate structure
            if not self._validate_extraction(structured_data):
                raise ValueError("Invalid extraction format from OpenAI")
            
            logger.info(f"Extracted {len(structured_data.get('items', []))} items from page {pdf_page.page_number}")
            
            return {
                'structured_data': structured_data,
                'raw_response': raw_response
            }
            
        except Exception as e:
            logger.error(f"Error extracting from page {pdf_page.id}: {str(e)}")
            raise