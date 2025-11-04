# design_agent/services/improved_gemini_renderer.py
"""
IMPROVED Gemini Rendering Service
Focus: Accurate layout matching, SKU validation, elevation only (no floor plans)
"""

import logging
import time
from typing import List, Optional
from io import BytesIO
from PIL import Image
from google import genai
from django.conf import settings
from django.core.files.base import ContentFile

from design_agent.models import PDFPage, Extraction, SKUMatch, Render

logger = logging.getLogger('design_agent')


class GeminiRenderer:
    """Generate photorealistic renders matching CAD layouts exactly"""
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash-image"
        logger.info(f"✅ Improved Gemini renderer initialized: {self.model_name}")
    
    def render_page(
        self,
        pdf_page: PDFPage,
        extraction: Extraction,
        sku_matches: List[SKUMatch],
        style_preference: str = "modern",
        base_render: Optional[Render] = None
    ) -> Render:
        """
        Generate or regenerate a render
        
        Args:
            pdf_page: PDFPage object
            extraction: Extraction with layout data
            sku_matches: List of matched SKUs
            style_preference: Design style
            base_render: If regenerating, the previous render to modify
        
        Returns:
            Render object with generated image
        """
        view_type = extraction.structured_data.get('view_type', 'elevation')
        
        # Skip floor plans - only render elevations
        if view_type.lower() == 'plan':
            logger.warning(f"⚠️ Skipping floor plan rendering for page {pdf_page.page_number}")
            render = Render.objects.create(
                project=pdf_page.pdf_document.project,
                pdf_page=pdf_page,
                style_preference=style_preference,
                status='skipped',
                error_message='Floor plan views are not rendered - elevation views only'
            )
            return render
        
        logger.info(f"🎨 Rendering {view_type} for page {pdf_page.page_number} (style: {style_preference})")
        logger.info(f"   SKUs matched: {len(sku_matches)}")
        
        # Determine version number
        version = 1
        parent_render = None
        if base_render:
            version = base_render.version + 1
            parent_render = base_render
        
        # Create render record
        render = Render.objects.create(
            project=pdf_page.pdf_document.project,
            pdf_page=pdf_page,
            style_preference=style_preference,
            status='processing',
            version=version,
            parent_render=parent_render
        )
        
        try:
            start_time = time.time()
            
            # Load CAD layout image
            with pdf_page.image_file.open('rb') as f:
                cad_layout = Image.open(BytesIO(f.read()))
            
            # Load SKU product images
            sku_images = []
            sku_details = []
            
            if sku_matches:
                for match in sku_matches:
                    sku = match.matched_sku
                    try:
                        if sku.image:
                            with sku.image.open('rb') as f:
                                img = Image.open(BytesIO(f.read()))
                                sku_images.append(img)
                                sku_details.append({
                                    'code': sku.code,
                                    'name': sku.name,
                                    'width': float(sku.width) if sku.width else None,
                                    'height': float(sku.height) if sku.height else None,
                                    'depth': float(sku.depth) if sku.depth else None,
                                    'finish': sku.finish
                                })
                                logger.info(f"  ✅ Loaded SKU image: {sku.code}")
                    except Exception as e:
                        logger.warning(f"  ⚠️ Failed to load image for SKU {sku.code}: {e}")
            
            # Build rendering prompt
            prompt = self._build_accurate_prompt(
                extraction=extraction,
                sku_details=sku_details,
                style=style_preference,
                is_regeneration=base_render is not None
            )
            
            # Generate image
            logger.info("🖼️ Calling Gemini 2.5 Flash Image...")
            
            # If regenerating, include base render as reference
            if base_render and base_render.image_file:
                try:
                    with base_render.image_file.open('rb') as f:
                        base_image = Image.open(BytesIO(f.read()))
                    generated_image = self._generate_with_gemini(
                        prompt=prompt,
                        layout_image=cad_layout,
                        product_images=sku_images,
                        reference_render=base_image
                    )
                except Exception as e:
                    logger.warning(f"Could not load base render, regenerating from scratch: {e}")
                    generated_image = self._generate_with_gemini(
                        prompt=prompt,
                        layout_image=cad_layout,
                        product_images=sku_images
                    )
            else:
                generated_image = self._generate_with_gemini(
                    prompt=prompt,
                    layout_image=cad_layout,
                    product_images=sku_images
                )
            
            # Save generated image
            if generated_image:
                image_io = BytesIO()
                generated_image.save(image_io, format='PNG')
                image_io.seek(0)
                
                filename = f"render_{render.id}_v{version}.png"
                render.image_file.save(filename, ContentFile(image_io.read()), save=False)
                logger.info(f"✅ Render saved: {filename}")
            else:
                raise ValueError("No image generated by Gemini")
            
            # Save metadata
            render.gemini_prompt = prompt
            render.generation_time = time.time() - start_time
            render.status = 'completed'
            render.save()
            
            # Deactivate old version if regenerating
            if base_render:
                base_render.is_active = False
                base_render.save()
                logger.info(f"📝 Deactivated old render version {base_render.version}")
            
            logger.info(f"✅ Render v{version} completed in {render.generation_time:.2f}s")
            return render
            
        except Exception as e:
            logger.error(f"❌ Render generation failed: {str(e)}")
            render.status = 'failed'
            render.error_message = str(e)
            render.save()
            raise
    
    def _generate_with_gemini(
        self,
        prompt: str,
        layout_image: Image.Image,
        product_images: List[Image.Image],
        reference_render: Optional[Image.Image] = None
    ) -> Image.Image:
        """
        Generate image using Gemini 2.5 Flash Image
        """
        try:
            # Build content array
            content = [prompt, layout_image]
            
            if reference_render:
                content.append(reference_render)
            
            if product_images:
                content.extend(product_images)
            
            # Call Gemini
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=content
            )
            
            # Extract image
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image_bytes = part.inline_data.data
                    generated_image = Image.open(BytesIO(image_bytes))
                    logger.info("✅ Image generated successfully")
                    return generated_image
            
            raise ValueError("No image found in Gemini response")
            
        except Exception as e:
            logger.error(f"❌ Gemini generation failed: {e}")
            raise
    
    def _build_accurate_prompt(
        self,
        extraction: Extraction,
        sku_details: List[dict],
        style: str,
        is_regeneration: bool = False
    ) -> str:
        """
        Build prompt focused on layout accuracy and SKU validation
        """
        view_type = extraction.structured_data.get('view_type', 'elevation')
        items = extraction.structured_data.get('items', [])
        
        # Build SKU list with details
        if sku_details:
            sku_list = []
            for sku in sku_details:
                desc = f"- **{sku['code']}**: {sku['name']}"
                if sku['width'] or sku['height'] or sku['depth']:
                    dims = []
                    if sku['width']:
                        dims.append(f"{sku['width']}\"W")
                    if sku['height']:
                        dims.append(f"{sku['height']}\"H")
                    if sku['depth']:
                        dims.append(f"{sku['depth']}\"D")
                    desc += f" ({' × '.join(dims)})"
                if sku['finish']:
                    desc += f" - {sku['finish']} finish"
                sku_list.append(desc)
            
            products_section = f"""**EXACT PRODUCTS TO RENDER ({len(sku_list)} items):**
{chr(10).join(sku_list)}

⚠️ CRITICAL: You MUST use these EXACT products in the rendering. Product images are provided."""
        else:
            products_section = "**Note:** Using standard kitchen/bathroom products based on layout."
        
        # Regeneration context
        regen_context = ""
        if is_regeneration:
            regen_context = """
**THIS IS A REGENERATION REQUEST:**
- A reference render is provided showing the previous version
- Make targeted modifications while preserving the overall layout and quality
- Only change elements that need updating (style, specific products, etc.)
"""
        
        # Build main prompt
        prompt = f"""Create a PHOTOREALISTIC {style} kitchen/bathroom rendering that EXACTLY matches the technical drawing layout.

{regen_context}

**LAYOUT TYPE:** {view_type.upper()} VIEW
This is an elevation view showing the front-facing arrangement of cabinets and appliances.

{products_section}

**CRITICAL LAYOUT REQUIREMENTS:**
1. **EXACT POSITIONING:** Every cabinet, appliance, and element must be in the EXACT position shown in the CAD drawing
2. **PRECISE DIMENSIONS:** Maintain exact width, height, and spacing from the technical drawing
3. **NO FLOOR PLAN:** This is an elevation view - render the front-facing view only (no top-down perspective)
4. **CABINET ALIGNMENT:** All cabinets must align horizontally and vertically as shown
5. **WALL CABINETS:** Position at correct height above base cabinets with proper spacing
6. **BASE CABINETS:** All at same floor level, aligned to create continuous countertop
7. **APPLIANCES:** Place exactly where indicated in the drawing with correct dimensions

**SKU VALIDATION:**
- Use the EXACT product images provided for each SKU
- Verify each product appears in its correct location
- Match product finishes and styles to the images
- Ensure recognizable features of each product are visible

**DESIGN STYLE: {style.upper()}**"""
        
        # Add style-specific instructions
        if style.lower() == "modern":
            prompt += """
- Ultra-clean lines with minimal ornamentation
- Handleless cabinets or sleek integrated handles
- Neutral color palette: whites, grays, with possible bold accent
- High-gloss or matte smooth finishes
- Seamlessly integrated appliances with matching panels
- Quartz or solid surface countertops
- LED under-cabinet lighting (subtle glow)
- Contemporary fixtures with geometric designs
- Glass tile or subway tile backsplash
- Hardwood or large-format tile flooring"""
        
        elif style.lower() == "traditional":
            prompt += """
- Classic raised panel cabinet doors with decorative details
- Ornate hardware: decorative knobs and pulls with vintage styling
- Warm wood tones (cherry, maple, walnut) or painted finishes (cream, sage green)
- Natural stone countertops: granite or marble with visible veining
- Crown molding along top of cabinets
- Detailed trim work and corbels
- Traditional faucets and fixtures with classic styling
- Ceramic tile or stone backsplash
- Hardwood flooring with visible grain"""
        
        elif style.lower() == "minimalist":
            prompt += """
- Absolutely clean, handleless flat-panel cabinets (push-to-open)
- Strict monochromatic color scheme (single color or tonal variations)
- No visible hardware whatsoever
- Completely concealed storage
- All appliances fully integrated and hidden behind panels
- Seamless surfaces with minimal joints
- Simple recessed lighting only
- Ultra-simple fixtures with no decoration
- Minimal or no backsplash (extended countertop)
- Clean flooring with no pattern"""
        
        prompt += f"""

**RENDERING QUALITY STANDARDS:**

1. **PHOTOREALISM:**
   - Professional architectural photography quality
   - Realistic materials with proper textures and reflections
   - Accurate lighting with natural shadows
   - Proper depth of field and perspective

2. **LIGHTING:**
   - Soft natural lighting from implied window (warm daylight)
   - Under-cabinet task lighting with subtle glow
   - Ambient ceiling lights creating even illumination
   - Realistic shadows and highlights on surfaces
   - No harsh shadows or overexposed areas

3. **MATERIALS & TEXTURES:**
   - Cabinets: Realistic wood grain or painted finish matching style
   - Countertops: Proper material texture (quartz sparkle, granite veining, etc.)
   - Backsplash: Accurate tile pattern and grout lines
   - Flooring: Natural wood grain or tile texture with realistic reflections
   - Hardware: Metallic sheen appropriate to style

4. **PERSPECTIVE & COMPOSITION:**
   - Straight-on elevation view (eye level, centered)
   - No distortion or wide-angle effects
   - All elements clearly visible and recognizable
   - Professional staging for client presentation

5. **DETAILS:**
   - Realistic cabinet doors and drawer fronts
   - Proper appliance details (control panels, handles, displays)
   - Accurate hardware placement and style
   - Clean, organized appearance

6. **MINIMAL STYLING:**
   - DO include: Small fruit bowl, 1-2 plants, dish towel, cookbook
   - DO NOT include: Excessive clutter, people, pets
   - Keep countertops mostly clear to show the design

**VERIFICATION CHECKLIST:**
✓ Layout matches CAD drawing exactly (verify each element position)
✓ All {len(sku_details)} SKU products are visible and recognizable
✓ Dimensions and proportions match technical drawing
✓ Style ({style}) is consistently applied throughout
✓ Professional photography-quality lighting and materials
✓ Clean, client-ready presentation

**TOTAL ITEMS IN LAYOUT:** {len(items)}
**VIEW TYPE:** {view_type}

Generate a stunning, accurate, photorealistic rendering that precisely represents this {style} kitchen/bathroom design."""

        return prompt
    
    
    # def _build_accurate_prompt(
    #     self,
    #     extraction: Extraction,
    #     sku_details: List[dict],
    #     style: str,
    #     is_regeneration: bool = False
    # ) -> str:
    #     """
    #     Build prompt focused on EXACT layout replication
    #     """
    #     view_type = extraction.structured_data.get('view_type', 'elevation')
    #     items = extraction.structured_data.get('items', [])
        
    #     # Build SKU list with details
    #     if sku_details:
    #         sku_list = []
    #         for sku in sku_details:
    #             desc = f"- **{sku['code']}**: {sku['name']}"
    #             if sku['width'] or sku['height'] or sku['depth']:
    #                 dims = []
    #                 if sku['width']:
    #                     dims.append(f"{sku['width']}\"W")
    #                 if sku['height']:
    #                     dims.append(f"{sku['height']}\"H")
    #                 if sku['depth']:
    #                     dims.append(f"{sku['depth']}\"D")
    #                 desc += f" ({' × '.join(dims)})"
    #             if sku['finish']:
    #                 desc += f" - {sku['finish']} finish"
    #             sku_list.append(desc)
            
    #         products_section = f"""**EXACT PRODUCTS TO RENDER ({len(sku_list)} items):**
    # {chr(10).join(sku_list)}

    # ⚠️ CRITICAL: You MUST use these EXACT products in the rendering. Product images are provided."""
    #     else:
    #         products_section = "**Note:** Using standard kitchen/bathroom products based on layout."
        
    #     # Regeneration context
    #     regen_context = ""
    #     if is_regeneration:
    #         regen_context = """
    # **THIS IS A REGENERATION REQUEST:**
    # - A reference render is provided showing the previous version
    # - Make targeted modifications while preserving the overall layout and quality
    # - Only change elements that need updating (style, specific products, etc.)
    # """
        
    #     # Build main prompt with EXTREME emphasis on layout accuracy
    #     prompt = f"""You are creating a PHOTOREALISTIC {style} kitchen/bathroom rendering that MUST be a PIXEL-PERFECT match to the technical CAD drawing provided.

    # {regen_context}

    # **🎯 PRIMARY OBJECTIVE: EXACT LAYOUT REPLICATION**
    # This is NOT a creative exercise. This is architectural visualization where ACCURACY IS EVERYTHING.
    # The CAD drawing is your ONLY source of truth for ALL spatial relationships.

    # **LAYOUT TYPE:** {view_type.upper()} VIEW - Front-facing elevation (NOT floor plan, NOT perspective)

    # {products_section}

    # ** CRITICAL LAYOUT MATCHING RULES (NON-NEGOTIABLE):**

    # 1. **TREAT THE CAD DRAWING AS A BLUEPRINT - EXACT PIXEL-TO-PIXEL MATCHING:**
    # - Every cabinet, appliance, and element MUST be in the EXACT position shown
    # - Use the CAD drawing as a direct overlay template
    # - Match EVERY dimension precisely - no creative interpretation
    # - If a cabinet is 18" wide in the drawing, it MUST be 18" wide in the render
    # - If two cabinets touch in the drawing, they MUST touch in the render (no gaps)
    # - If there's a 3" gap in the drawing, maintain EXACTLY 3" gap in render

    # 2. **HORIZONTAL ALIGNMENT (CRITICAL):**
    # - ALL base cabinets MUST have their tops at IDENTICAL height (forming continuous countertop)
    # - ALL wall cabinets MUST have their bottoms at IDENTICAL height
    # - Verify every cabinet aligns with its neighbors - no vertical offsets
    # - Countertop MUST be one continuous level surface across all base cabinets
    # - NO sagging, no elevation changes, no perspective distortion

    # 3. **VERTICAL ALIGNMENT (CRITICAL):**
    # - Cabinet edges MUST align perfectly when stacked or adjacent
    # - Wall cabinets MUST align vertically with base cabinets below them
    # - Check that cabinet columns form perfect vertical lines
    # - Doors and drawer fronts must align across adjacent cabinets

    # 4. **SPACING & GAPS:**
    # - Preserve EXACT spacing between elements as shown in CAD
    # - If cabinets are flush (touching), show NO gap in render
    # - If there's measured space, maintain EXACT measurement
    # - Gap between wall and base cabinets: maintain EXACT vertical distance shown

    # 5. **WIDTH PROPORTIONS:**
    # - Read the dimension labels in the CAD drawing carefully
    # - A 36" cabinet next to an 18" cabinet MUST show 2:1 width ratio
    # - Total wall width in render MUST match CAD drawing proportions
    # - Check: do all cabinet widths add up to the total width shown?

    # 6. **HEIGHT PROPORTIONS:**
    # - Wall cabinet heights MUST match specified dimensions
    # - Base cabinet heights MUST be standard (typically 34.5" + countertop)
    # - Toe kick space at bottom MUST be visible and correct height
    # - Appliance heights MUST match their SKU specifications exactly

    # 7. **APPLIANCE INTEGRATION:**
    # - Built-in appliances (dishwasher, range, microwave) MUST fit EXACTLY in their designated spaces
    # - NO gaps around built-in appliances unless shown in CAD
    # - Appliance widths MUST match openings precisely
    # - Range hood positioned EXACTLY as shown above range

    # 8. **VIEW ANGLE - PURE ELEVATION:**
    # - This is a STRAIGHT-ON, ORTHOGRAPHIC elevation view (like an architect's drawing)
    # - Camera is PERPENDICULAR to the wall (0° rotation)
    # - NO perspective distortion (parallel lines stay parallel)
    # - NO vanishing points - this is NOT a perspective view
    # - NO fisheye or wide angle effects
    # - Think: architectural presentation drawing, not interior photography

    # 9. **DEPTH PERCEPTION:**
    # - While this is an elevation, show subtle depth through:
    #     * Shadow lines between adjacent cabinets (very subtle)
    #     * Slight highlight on cabinet edges
    #     * Handle/knob shadows
    # - But DO NOT rotate view or show side angles

    # **LAYOUT VERIFICATION CHECKLIST - CONFIRM BEFORE RENDERING:**
    # □ Counted all cabinets in CAD - same count will appear in render
    # □ Measured relative widths - proportions match exactly
    # □ Checked horizontal alignment - all base tops level, all wall bottoms level  
    # □ Verified spacing - gaps match CAD exactly
    # □ Confirmed appliance placements match openings
    # □ View is pure front elevation (no perspective/rotation)
    # □ Cabinet arrangement left-to-right matches CAD perfectly

    # ---

    # **DESIGN STYLE: {style.upper()}**
    # (Style applies to finishes/materials ONLY - layout is fixed by CAD)"""
        
    #     # Add style-specific instructions (more concise)
    #     if style.lower() == "modern":
    #         prompt += """

    # **Modern Style Characteristics:**
    # - Flat-panel, handleless cabinet doors (push-to-open) OR sleek integrated bar handles
    # - High-gloss OR ultra-matte smooth finishes
    # - Colors: White, light gray, dark gray, or bold accent color
    # - Quartz countertops with minimal veining (solid colors)
    # - Glass or high-gloss tile backsplash
    # - Integrated appliances with matching cabinet panels where possible
    # - LED under-cabinet lighting (soft glow)
    # - Minimal hardware - clean and simple
    # - Large format tile or hardwood flooring"""
        
    #     elif style.lower() == "traditional":
    #         prompt += """

    # **Traditional Style Characteristics:**
    # - Raised panel cabinet doors with decorative details
    # - Ornate hardware: decorative knobs and pulls (bronze, brass, or brushed nickel)
    # - Warm wood tones (cherry, maple, walnut) OR painted (cream, sage, white)
    # - Granite or marble countertops with natural veining
    # - Crown molding and decorative trim
    # - Classic tile backsplash (subway or decorative patterns)
    # - Traditional faucet and fixture styles
    # - Natural wood or ceramic tile flooring with visible grain/texture"""
        
    #     elif style.lower() == "minimalist":
    #         prompt += """

    # **Minimalist Style Characteristics:**
    # - Completely flat cabinet doors with NO handles (push-open)
    # - Monochromatic palette (single color or very subtle tonal variations)
    # - NO visible hardware whatsoever
    # - Seamless integration - appliances hidden behind panels
    # - Ultra-smooth surfaces with invisible seams
    # - Simple recessed lighting only
    # - Minimal or no backsplash (countertop extends up)
    # - Clean flooring with no pattern"""
        
    #     prompt += f"""

    # ---

    # **RENDERING QUALITY REQUIREMENTS:**

    # **1. PHOTOREALISM:**
    # - Professional architectural photography quality
    # - Realistic materials with accurate texture mapping
    # - Proper reflections on glossy surfaces (not overdone)
    # - Natural lighting that reveals form without harsh shadows
    # - High resolution detail

    # **2. LIGHTING (Natural & Realistic):**
    # - Primary: Soft natural daylight from front (as if from a window facing the elevation)
    # - Secondary: Under-cabinet LED strips (warm white, subtle glow under wall cabinets)
    # - Ambient: Soft overhead lighting (recessed ceiling lights implied)
    # - NO direct sunlight creating harsh shadows
    # - NO dramatic side lighting that distorts perception
    # - Even, well-lit presentation that shows all details clearly

    # **3. MATERIALS & TEXTURES:**
    # - Cabinet finish: Appropriate to style (wood grain, matte paint, high-gloss lacquer)
    # - Countertop: Realistic stone/quartz texture with proper reflectivity
    # - Backsplash: Accurate tile pattern with visible grout lines (not blurred)
    # - Hardware: Metallic sheen with subtle reflections
    # - Appliances: Stainless steel or integrated panels matching cabinets
    # - Floor: Appropriate texture (wood grain, tile pattern) - but keep minimal/blurred as elevation view

    # **4. DETAILS:**
    # - Cabinet door panels clearly defined
    # - Drawer fronts distinguishable from doors
    # - Handles/knobs properly sized and positioned
    # - Appliance control panels visible (ranges, dishwashers)
    # - Range hood ventilation details
    # - Toe kick shadow line at base of cabinets
    # - Reveals (small gaps) between doors appropriate to style

    # **5. MINIMAL STAGING (Keep Focus on Design):**
    # - Include ONLY: Small bowl of fruit OR single plant, one dish towel, maybe one cookbook
    # - Countertops should be 95% clear
    # - NO people, pets, excessive decorations
    # - NO clutter - this is a presentation drawing
    # - Goal: Show the kitchen design clearly, not lifestyle photography

    # **6. COLOR ACCURACY:**
    # - Match finish colors to style specification
    # - Consistent color temperature throughout (warm or cool based on style)
    # - Natural color rendering (no oversaturation or color shifts)

    # ---

    # **COMMON MISTAKES TO AVOID:**

    # DO NOT create artistic interpretation - this is technical visualization
    # DO NOT adjust proportions "to look better" - match CAD exactly
    # DO NOT add perspective distortion or wide-angle effects  
    # DO NOT change spacing between elements
    # DO NOT reorder cabinets or appliances
    # DO NOT omit any elements shown in CAD drawing
    # DO NOT add elements not shown in CAD drawing
    # DO NOT show the kitchen from an angle - pure front elevation only
    # DO NOT create gaps where cabinets should be flush
    # DO NOT misalign cabinet heights (base tops, wall bottoms)

    # ---

    # **FINAL VERIFICATION:**

    # Before finalizing the render, verify:
    # ✓ Layout matches CAD drawing with <1% deviation
    # ✓ All {len(sku_details)} SKU products are visible and recognizable  
    # ✓ Cabinet widths proportional to CAD measurements
    # ✓ Horizontal and vertical alignment is perfect
    # ✓ Style ({style}) is applied consistently
    # ✓ Photorealistic quality suitable for client presentation
    # ✓ View is pure elevation (no rotation or perspective)

    # **TOTAL ITEMS:** {len(items)}
    # **VIEW TYPE:** {view_type}

    # Generate a stunning, LAYOUT-ACCURATE, photorealistic {style} rendering that precisely represents this design."""

    #     return prompt


    def render_all_pages(
        self,
        project,
        style_preference: str = "modern"
    ) -> List[Render]:
        """
        Generate renders for all elevation pages (skip floor plans)
        """
        logger.info(f"🎨 Starting batch rendering for project {project.id}")
        
        pdf_document = project.pdf_document
        pdf_pages = pdf_document.pages.all().order_by('page_number')
        
        renders = []
        skipped = 0
        
        for pdf_page in pdf_pages:
            try:
                if not hasattr(pdf_page, 'extraction'):
                    logger.warning(f"⚠️ No extraction for page {pdf_page.page_number}, skipping")
                    continue
                
                extraction = pdf_page.extraction
                view_type = extraction.structured_data.get('view_type', 'elevation')
                
                # Skip floor plans
                if view_type.lower() == 'plan':
                    logger.info(f"⏭️ Skipping floor plan on page {pdf_page.page_number}")
                    skipped += 1
                    continue
                
                # Get SKU matches
                sku_matches = list(extraction.sku_matches.all())
                
                logger.info(f"📄 Rendering page {pdf_page.page_number} ({view_type}, {len(sku_matches)} SKUs)")
                
                # Generate render
                render = self.render_page(
                    pdf_page=pdf_page,
                    extraction=extraction,
                    sku_matches=sku_matches,
                    style_preference=style_preference
                )
                
                if render.status == 'completed':
                    renders.append(render)
                
            except Exception as e:
                logger.error(f"❌ Failed to render page {pdf_page.page_number}: {str(e)}")
                continue
        
        logger.info(f"✅ Batch rendering complete: {len(renders)} successful, {skipped} skipped (floor plans)")
        return renders