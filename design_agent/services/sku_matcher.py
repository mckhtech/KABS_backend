"""
SKU Matching Service - IMPROVED
Code-first matching with fuzzy fallback and dimension validation
"""

import logging
from typing import List, Dict, Optional
from django.db.models import Q
from decimal import Decimal
from difflib import SequenceMatcher

from design_agent.models import SKUCatalog, Extraction, SKUMatch

logger = logging.getLogger('design_agent')


class SKUMatcher:
    """Match extracted labels to SKUs using multi-strategy approach"""
    
    def __init__(self, dimension_tolerance: float = 5.0):
        """
        Args:
            dimension_tolerance: Tolerance in inches for dimension matching (default: ±5")
        """
        self.tolerance = Decimal(str(dimension_tolerance))
        logger.info(f"🔗 SKU Matcher initialized (tolerance: {dimension_tolerance}\")")
    
    def match_extraction(self, extraction: Extraction) -> List[SKUMatch]:
        """
        Match all items from an extraction to SKUs
        
        Args:
            extraction: Extraction object with structured_data
        
        Returns:
            List of SKUMatch objects
        """
        logger.info(f"🔗 Matching SKUs for extraction {extraction.id}")
        
        items = extraction.structured_data.get('items', [])
        sku_matches = []
        
        logger.info(f"   Found {len(items)} items to match")
        
        for idx, item in enumerate(items, 1):
            label = item.get('label', '').strip()
            category = item.get('category', '')
            dimensions = item.get('dimensions', {})
            position = item.get('position', {})
            
            if not label:
                logger.warning(f"   Item {idx}: No label, skipping")
                continue
            
            logger.info(f"   Item {idx}: Processing '{label}' (category: {category})")
            
            # Find matching SKUs using multi-strategy approach
            matched_skus = self.find_matching_skus(
                label=label,
                category=category,
                dimensions=dimensions,
                max_results=4
            )
            
            if matched_skus:
                best_match = matched_skus[0]
                alternatives = matched_skus[1:4]
                
                # Create SKUMatch record
                sku_match = SKUMatch.objects.create(
                    extraction=extraction,
                    label_text=label,
                    label_category=category,
                    matched_sku=best_match['sku'],
                    match_score=best_match['score'],
                    position_data={
                        'position': position,
                        'dimensions': dimensions,
                        'notes': item.get('notes', '')
                    },
                    alternative_skus=[
                        {
                            'sku_code': alt['sku'].code,
                            'score': alt['score'],
                            'dimensions': {
                                'width': float(alt['sku'].width) if alt['sku'].width else None,
                                'height': float(alt['sku'].height) if alt['sku'].height else None,
                                'depth': float(alt['sku'].depth) if alt['sku'].depth else None
                            }
                        }
                        for alt in alternatives
                    ]
                )
                
                sku_matches.append(sku_match)
                
                # Detailed logging
                score_emoji = "🟢" if best_match['score'] >= 0.95 else "🟡" if best_match['score'] >= 0.8 else "🟠"
                logger.info(f"   {score_emoji} Matched '{label}' → {best_match['sku'].code} (score: {best_match['score']:.3f})")
                if best_match.get('match_method'):
                    logger.info(f"      Method: {best_match['match_method']}")
            else:
                logger.warning(f"   🔴 No match found for: '{label}' (category: {category})")
        
        logger.info(f"✅ Matched {len(sku_matches)}/{len(items)} items")
        return sku_matches
    
    def find_matching_skus(
        self,
        label: str,
        category: str,
        dimensions: Dict[str, float],
        max_results: int = 4
    ) -> List[Dict]:
        """
        Find matching SKUs with MULTI-STRATEGY approach:
        Priority: Exact Code > Normalized Code > Fuzzy Code > Dimension Match
        """
        
        db_category = self._map_category(category, label)
        label_upper = label.upper().strip()
        
        logger.debug(f"      Searching for: '{label}' (mapped category: {db_category})")
        
        exact_match = SKUCatalog.objects.filter(
            is_active=True,
            code__iexact=label
        ).first()
        
        if exact_match:
            logger.debug(f"      ✅ EXACT match found: {exact_match.code}")
            return [{
                'sku': exact_match,
                'score': 1.0,
                'match_method': 'exact_code'
            }]
        
        normalized_label = self._normalize_code(label_upper)
        
        for sku in SKUCatalog.objects.filter(is_active=True):
            normalized_sku_code = self._normalize_code(sku.code.upper())
            if normalized_sku_code == normalized_label:
                logger.debug(f"      ✅ NORMALIZED match: {sku.code}")
                return [{
                    'sku': sku,
                    'score': 0.98,
                    'match_method': 'normalized_code'
                }]
        
        fuzzy_candidates = []
        
        # Filter by category first to reduce search space
        category_skus = SKUCatalog.objects.filter(
            is_active=True,
            category=db_category
        )
        
        logger.debug(f"      Checking {category_skus.count()} SKUs in category '{db_category}'")
        
        for sku in category_skus:
            similarity = self._code_similarity(label_upper, sku.code.upper())
            
            if similarity >= 0.75:  # 75% similarity threshold
                fuzzy_candidates.append({
                    'sku': sku,
                    'score': similarity * 0.95,  # Max 0.95 for fuzzy
                    'match_method': f'fuzzy_code ({similarity:.2f})'
                })
        
        # Sort by similarity
        fuzzy_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        if fuzzy_candidates:
            logger.debug(f" ✅ FUZZY match: {fuzzy_candidates[0]['sku'].code} ({fuzzy_candidates[0]['score']:.3f})")
            return fuzzy_candidates[:max_results]
        
        if dimensions and any(dimensions.values()):
            logger.debug(f"      Trying dimension-based matching...")
            
            dim_candidates = []
            
            for sku in category_skus:
                dim_score = self._calculate_match_score(dimensions, sku)
                
                if dim_score >= 0.7:  # 70% dimension match
                    dim_candidates.append({
                        'sku': sku,
                        'score': dim_score * 0.8,  # Max 0.8 for dimension-only
                        'match_method': f'dimensions ({dim_score:.2f})'
                    })
            
            dim_candidates.sort(key=lambda x: x['score'], reverse=True)
            
            if dim_candidates:
                logger.debug(f"      ✅ DIMENSION match: {dim_candidates[0]['sku'].code} ({dim_candidates[0]['score']:.3f})")
                return dim_candidates[:max_results]
        
        logger.debug(f" No match found for '{label}'")
        return []
    
    def _normalize_code(self, code: str) -> str:
        """Normalize SKU code by removing separators and spaces"""
        return code.replace('-', '').replace('_', '').replace(' ', '').strip()
    
    def _map_category(self, extracted_category: str, label: str) -> str:
        """
        Map extracted category to database category
        
        Args:
            extracted_category: Category from extraction
            label: Product code for fallback parsing
        """
        category_lower = extracted_category.lower()
        
        # Direct mappings
        if 'cabinet' in category_lower or 'wall' in category_lower:
            return 'cabinet'
        elif 'appliance' in category_lower:
            return 'appliance'
        elif 'tile' in category_lower or 'mosaic' in category_lower:
            return 'tile'
        elif 'panel' in category_lower or 'filler' in category_lower:
            return 'cabinet'  # Panels/fillers are in cabinet category
        
        # Fallback: parse label prefix
        label_upper = label.upper()
        
        # Cabinet codes
        if any(label_upper.startswith(prefix) for prefix in [
            'BC', 'SB', 'DB', 'B', 'BTB', 'W', 'WP', 'OV', 'VP',
            'FLAT', 'USF', 'FL', 'PNL'
        ]):
            return 'cabinet'
        
        # Appliance codes
        if any(label_upper.startswith(prefix) for prefix in [
            'BI-', 'DISH', 'CKT', 'SFU', 'CPRU', 'MW', 'REF'
        ]):
            return 'appliance'
        
        # Default to cabinet (most common)
        logger.debug(f"      Unknown category for '{label}', defaulting to 'cabinet'")
        return 'cabinet'
    
    def _calculate_match_score(self, target_dims: Dict, sku: SKUCatalog) -> float:
        """
        Calculate how well SKU matches target dimensions
        
        Returns:
            Score from 0.0 (no match) to 1.0 (perfect match)
        """
        scores = []
        
        for dim_name in ['width', 'height', 'depth']:
            target_value = target_dims.get(dim_name)
            sku_value = getattr(sku, dim_name)
            
            if target_value and sku_value:
                # Calculate difference
                diff = abs(float(sku_value) - target_value)
                
                # Score: 1.0 if exact, decreases linearly
                if diff <= float(self.tolerance):
                    score = 1.0 - (diff / float(self.tolerance))
                    scores.append(score)
                else:
                    scores.append(0.0)
            elif not target_value and not sku_value:
                # Both missing - neutral
                continue
            else:
                # One missing - slight penalty
                scores.append(0.6)
        
        # Average of all dimension scores
        if scores:
            return sum(scores) / len(scores)
        else:
            # No dimensions to compare
            return 0.5
    
    def _code_similarity(self, code1: str, code2: str) -> float:
        """Calculate similarity between two SKU codes (0-1)"""
        return SequenceMatcher(None, code1, code2).ratio()