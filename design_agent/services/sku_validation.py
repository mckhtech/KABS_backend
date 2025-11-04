# design_agent/services/sku_validation.py
"""
SKU Image Validation - Ensures all matched SKUs have images before rendering
"""

import logging
from typing import Dict, List
from django.db.models import Q

from design_agent.models import Project, SKUMatch, SKUCatalog

logger = logging.getLogger('design_agent')


class SKUValidator:
    """Validate SKU data completeness before rendering"""
    
    def validate_project_skus(self, project: Project) -> Dict:
        """
        Validate all SKUs for a project before rendering
        
        Returns:
            {
                "valid": True/False,
                "total_skus": 40,
                "skus_with_images": 38,
                "missing_images": [
                    {"sku_code": "DB18-3", "sku_name": "...", "pages": [1, 2]},
                ],
                "skus_without_prices": [
                    {"sku_code": "W361824", "sku_name": "...", "pages": [3]},
                ],
                "validation_summary": "2 SKUs missing images, 1 SKU without price"
            }
        """
        logger.info(f"🔍 Validating SKUs for project {project.id}")
        
        # Get all SKU matches for this project
        pdf_document = project.pdf_document
        sku_matches = SKUMatch.objects.filter(
            extraction__pdf_page__pdf_document=pdf_document
        ).select_related('matched_sku', 'extraction__pdf_page')
        
        if not sku_matches.exists():
            return {
                "valid": False,
                "error": "No SKU matches found. Run match_skus first.",
                "total_skus": 0
            }
        
        # Track validation results
        total_skus = sku_matches.count()
        missing_images = []
        missing_prices = []
        skus_with_images = 0
        
        # Group SKUs by code to avoid duplicates in report
        sku_groups = {}
        
        for match in sku_matches:
            sku = match.matched_sku
            page_num = match.extraction.pdf_page.page_number
            
            if sku.code not in sku_groups:
                sku_groups[sku.code] = {
                    'sku': sku,
                    'pages': [],
                    'has_image': bool(sku.image),
                    'has_price': sku.price is not None
                }
            
            sku_groups[sku.code]['pages'].append(page_num)
        
        # Analyze each unique SKU
        for sku_code, data in sku_groups.items():
            sku = data['sku']
            pages = sorted(set(data['pages']))
            
            # Check image
            if not data['has_image']:
                missing_images.append({
                    'sku_code': sku.code,
                    'sku_name': sku.name,
                    'pages': pages,
                    'category': sku.category
                })
            else:
                skus_with_images += 1
            
            # Check price
            if not data['has_price']:
                missing_prices.append({
                    'sku_code': sku.code,
                    'sku_name': sku.name,
                    'pages': pages,
                    'category': sku.category
                })
        
        # Determine if valid for rendering
        # Renders can proceed even without some images, but we warn user
        is_valid = len(missing_images) == 0
        
        # Build summary message
        issues = []
        if missing_images:
            issues.append(f"{len(missing_images)} SKUs missing images")
        if missing_prices:
            issues.append(f"{len(missing_prices)} SKUs without prices")
        
        summary = ", ".join(issues) if issues else "All SKUs validated successfully"
        
        # Log results
        if missing_images:
            logger.warning(f"⚠️ Missing images for {len(missing_images)} SKUs:")
            for item in missing_images:
                logger.warning(f"   - {item['sku_code']} ({item['sku_name']}) on pages {item['pages']}")
        
        if missing_prices:
            logger.warning(f"⚠️ Missing prices for {len(missing_prices)} SKUs:")
            for item in missing_prices:
                logger.warning(f"   - {item['sku_code']} ({item['sku_name']}) on pages {item['pages']}")
        
        if is_valid:
            logger.info(f"✅ All {total_skus} SKUs validated successfully")
        
        return {
            "valid": is_valid,
            "can_render": True,  # Allow rendering even with missing images
            "can_generate_pricing": len(missing_prices) < total_skus,  # Need at least some prices
            "total_skus": total_skus,
            "unique_skus": len(sku_groups),
            "skus_with_images": skus_with_images,
            "skus_with_prices": len(sku_groups) - len(missing_prices),
            "missing_images": missing_images,
            "missing_prices": missing_prices,
            "validation_summary": summary,
            "recommendations": self._get_recommendations(missing_images, missing_prices)
        }
    
    def _get_recommendations(self, missing_images: List, missing_prices: List) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        if missing_images:
            recommendations.append(
                f"Upload images for {len(missing_images)} SKUs in the admin panel to improve render quality"
            )
            recommendations.append(
                "Renders will still generate but may use generic placeholders for items without images"
            )
        
        if missing_prices:
            recommendations.append(
                f"Add prices for {len(missing_prices)} SKUs to enable accurate cost calculations"
            )
        
        if not missing_images and not missing_prices:
            recommendations.append("Project is ready for rendering and pricing generation")
        
        return recommendations
    
    def get_sku_images_for_page(self, pdf_page) -> List[Dict]:
        """
        Get all SKU images for a specific page (used by renderer)
        
        Returns:
            [
                {
                    'sku_code': 'W361824',
                    'sku_name': 'Wall Cabinet 36x18x24',
                    'image_path': '/media/sku_images/...',
                    'has_image': True,
                    'dimensions': {'width': 36, 'height': 18, 'depth': 24}
                },
                ...
            ]
        """
        if not hasattr(pdf_page, 'extraction'):
            return []
        
        extraction = pdf_page.extraction
        sku_matches = extraction.sku_matches.select_related('matched_sku').all()
        
        sku_images = []
        
        for match in sku_matches:
            sku = match.matched_sku
            
            sku_images.append({
                'sku_code': sku.code,
                'sku_name': sku.name,
                'image_path': sku.image.path if sku.image else None,
                'image_url': sku.image.url if sku.image else None,
                'has_image': bool(sku.image),
                'dimensions': {
                    'width': float(sku.width) if sku.width else None,
                    'height': float(sku.height) if sku.height else None,
                    'depth': float(sku.depth) if sku.depth else None
                },
                'finish': sku.finish,
                'category': sku.category
            })
        
        return sku_images
    