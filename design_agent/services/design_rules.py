# design_agent/services/design_rules.py
"""
Kitchen & Bath Design Rules
Hard-coded rules from client rulebooks - NO RAG NEEDED for MVP

Start with essential rules, expand as needed
"""

# Kitchen Design Rules
KITCHEN_RULES = {
    # Spacing & Clearances (inches)
    'min_aisle_width': 42,
    'min_work_aisle_width': 48,  # Between two work areas
    'min_walkway_width': 36,
    'min_countertop_depth': 24,
    'max_countertop_depth': 25,
    'min_island_clearance': 42,  # Around all sides
    'max_distance_sink_to_stove': 72,  # Work triangle
    
    # Cabinet Heights (inches)
    'standard_base_cabinet_height': 34.5,
    'standard_countertop_thickness': 1.5,
    'total_counter_height': 36,  # Base + countertop
    'min_upper_cabinet_height': 12,
    'max_upper_cabinet_height': 42,
    'standard_upper_cabinet_bottom': 54,  # From floor
    'min_clearance_counter_to_upper': 18,
    
    # Appliance Requirements
    'dishwasher_location': 'within_36_inches_of_sink',
    'dishwasher_width': 24,
    'standard_range_width': 30,
    'refrigerator_clearance_front': 48,  # For door swing
    'refrigerator_clearance_side': 15,  # If against wall
    
    # Ventilation
    'range_hood_min_width': 'match_cooktop_width',
    'range_hood_height_above_cooktop': 30,
    
    # Electrical
    'gfci_required_near_sink': True,
    'min_outlets_per_counter': 2,
    'max_outlet_spacing': 48,
}

# Bathroom Design Rules
BATHROOM_RULES = {
    # Clearances (inches)
    'toilet_front_clearance': 30,
    'toilet_side_clearance': 15,  # From centerline
    'vanity_front_clearance': 30,
    'shower_min_interior': 30,  # Square
    'tub_access_clearance': 30,
    
    # Fixtures
    'toilet_rough_in': 12,  # From wall to centerline
    'standard_vanity_height': 32,
    'comfort_height_vanity': 36,
    'standard_vanity_depth': 21,
    
    # Lighting & Ventilation
    'gfci_required': True,
    'exhaust_fan_required': True,
    'min_lighting_lumens': 75,  # Per square foot
}

# General Design Guidelines
DESIGN_GUIDELINES = {
    'modern_style': {
        'cabinet_style': 'flat_panel',
        'hardware': 'minimal_or_hidden',
        'color_palette': 'neutral_with_accent',
        'countertop': 'quartz_or_solid_surface',
    },
    'traditional_style': {
        'cabinet_style': 'raised_panel',
        'hardware': 'decorative_knobs_pulls',
        'color_palette': 'warm_wood_tones',
        'countertop': 'granite_or_marble',
    },
    'minimalist_style': {
        'cabinet_style': 'slab_door',
        'hardware': 'integrated_or_none',
        'color_palette': 'monochromatic',
        'countertop': 'seamless_solid_surface',
    }
}


class DesignValidator:
    """Validate extracted layouts against design rules"""
    
    def __init__(self, room_type='kitchen'):
        """
        Args:
            room_type: 'kitchen' or 'bathroom'
        """
        self.room_type = room_type
        self.rules = KITCHEN_RULES if room_type == 'kitchen' else BATHROOM_RULES
    
    def validate_layout(self, extraction_data):
        """
        Validate layout against design rules
        
        Args:
            extraction_data: Structured data from extraction
        
        Returns:
            dict with validation results and warnings
        """
        items = extraction_data.get('items', [])
        warnings = []
        errors = []
        
        # Extract item positions and dimensions
        cabinets = [i for i in items if 'cabinet' in i.get('category', '').lower()]
        appliances = [i for i in items if 'appliance' in i.get('category', '').lower()]
        
        if self.room_type == 'kitchen':
            # Check aisle widths
            aisle_warnings = self._check_aisle_widths(items)
            warnings.extend(aisle_warnings)
            
            # Check appliance placement
            appliance_warnings = self._check_appliance_placement(appliances)
            warnings.extend(appliance_warnings)
            
            # Check cabinet heights
            cabinet_warnings = self._check_cabinet_heights(cabinets)
            warnings.extend(cabinet_warnings)
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'rules_checked': len(warnings) + len(errors)
        }
    
    def _check_aisle_widths(self, items):
        """Check if aisles meet minimum width requirements"""
        warnings = []
        
        # Simple heuristic: check horizontal spacing between items
        # (More sophisticated version would use full spatial analysis)
        
        sorted_by_x = sorted(items, key=lambda x: x.get('position', {}).get('x', 0))
        
        for i in range(len(sorted_by_x) - 1):
            item1 = sorted_by_x[i]
            item2 = sorted_by_x[i + 1]
            
            x1_end = item1.get('position', {}).get('x', 0) + item1.get('dimensions', {}).get('width', 0)
            x2_start = item2.get('position', {}).get('x', 0)
            
            gap = x2_start - x1_end
            
            if 0 < gap < self.rules['min_aisle_width']:
                warnings.append({
                    'type': 'aisle_width',
                    'message': f'Aisle width ({gap:.1f}") is less than minimum ({self.rules["min_aisle_width"]}")',
                    'severity': 'warning',
                    'items': [item1.get('label'), item2.get('label')]
                })
        
        return warnings
    
    def _check_appliance_placement(self, appliances):
        """Check appliance placement rules"""
        warnings = []
        
        # Find dishwasher and sink
        dishwasher = next((a for a in appliances if 'dish' in a.get('label', '').lower()), None)
        sink = next((a for a in appliances if 'sink' in a.get('label', '').lower()), None)
        
        if dishwasher and sink:
            # Calculate distance
            dx_pos = dishwasher.get('position', {}).get('x', 0)
            sink_pos = sink.get('position', {}).get('x', 0)
            distance = abs(dx_pos - sink_pos)
            
            if distance > 36:
                warnings.append({
                    'type': 'appliance_placement',
                    'message': f'Dishwasher is {distance:.1f}" from sink (recommended: within 36")',
                    'severity': 'warning'
                })
        
        return warnings
    
    def _check_cabinet_heights(self, cabinets):
        """Check cabinet height specifications"""
        warnings = []
        
        upper_cabinets = [c for c in cabinets if 'wall' in c.get('category', '').lower() or c.get('position', {}).get('y', 0) > 40]
        
        for cabinet in upper_cabinets:
            height = cabinet.get('dimensions', {}).get('height', 0)
            
            if height > self.rules['max_upper_cabinet_height']:
                warnings.append({
                    'type': 'cabinet_height',
                    'message': f'Upper cabinet height ({height}") exceeds maximum ({self.rules["max_upper_cabinet_height"]}")',
                    'severity': 'warning',
                    'item': cabinet.get('label')
                })
        
        return warnings
    
    def get_style_recommendations(self, style_preference):
        """Get style-specific recommendations for rendering"""
        return DESIGN_GUIDELINES.get(style_preference, DESIGN_GUIDELINES['modern_style'])


# Helper function for use in rendering
def apply_design_rules_to_prompt(extraction_data, style_preference, room_type='kitchen'):
    """
    Enhance rendering prompt with design rule compliance
    
    Returns:
        str: Additional prompt text with rules
    """
    validator = DesignValidator(room_type=room_type)
    validation_result = validator.validate_layout(extraction_data)
    
    prompt_additions = []
    
    # Add warnings as instructions
    if validation_result['warnings']:
        prompt_additions.append("\nDESIGN COMPLIANCE NOTES:")
        for warning in validation_result['warnings'][:3]:  # Limit to top 3
            prompt_additions.append(f"- {warning['message']}")
    
    # Add style guidelines
    style_rec = validator.get_style_recommendations(style_preference)
    prompt_additions.append("\nSTYLE SPECIFICATIONS:")
    prompt_additions.append(f"- Cabinet Style: {style_rec['cabinet_style'].replace('_', ' ').title()}")
    prompt_additions.append(f"- Hardware: {style_rec['hardware'].replace('_', ' ').title()}")
    prompt_additions.append(f"- Color Palette: {style_rec['color_palette'].replace('_', ' ').title()}")
    
    return "\n".join(prompt_additions)