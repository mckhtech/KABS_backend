"""
PDF Report Generator - FULLY DEBUGGED & FIXED
Creates final professional PDF reports with comprehensive error handling
"""

import logging
from io import BytesIO
from datetime import datetime
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, Image as RLImage, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.conf import settings
from PyPDF2 import PdfReader, PdfWriter
import traceback

from design_agent.models import Project, Render, Annotation
import sys

# Reconfigure stdout to handle UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

logger = logging.getLogger('design_agent')


class PDFReportGenerator:
    """Generate professional PDF reports for design projects"""
    
    def __init__(self, project: Project):
        self.project = project
        self.buffer = BytesIO()
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=0.75*inch
        )
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        self.story = []
    
    def _setup_custom_styles(self):
        """Create custom paragraph styles"""
        
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='Subsection',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='Price',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#27ae60'),
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        ))
    
    def generate_complete_report(self) -> BytesIO:
        """
        Generate complete PDF report with comprehensive error handling
        """
        logger.info(f"=== Starting PDF generation for project {self.project.id} ===")
        
        try:
            # Build each section with individual error handling
            logger.info("Adding cover page...")
            self._add_cover_page()
            
            logger.info("Adding project overview...")
            self._add_project_overview()
            
            logger.info("Adding renders section...")
            self._add_renders_section()
            
            logger.info("Adding specifications section...")
            self._add_specifications_section()
            
            logger.info("Adding pricing section...")
            self._add_pricing_section()
            
            logger.info("Adding annotations section...")
            self._add_annotations_section()
            
            logger.info("Adding footer...")
            self._add_footer_info()
            
            # Build ReportLab PDF
            logger.info("Building ReportLab PDF document...")
            self.doc.build(self.story)
            logger.info(f"ReportLab PDF built successfully, size: {self.buffer.tell()} bytes")
            
            # Merge with original CAD PDF
            logger.info("Attempting to merge with original CAD PDF...")
            final_pdf = self._merge_with_original_cad()
            
            logger.info(f"=== PDF generation completed successfully ===")
            return final_pdf
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR in generate_complete_report: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
    
    def _merge_with_original_cad(self):
        """
        Merge generated report with original CAD PDF
        Returns just the generated report if merge fails
        """
        try:
            # Check if project has PDF document
            if not hasattr(self.project, 'pdf_document') or not self.project.pdf_document:
                logger.warning("No PDF document found, returning generated report only")
                self.buffer.seek(0)
                return self.buffer
            
            pdf_document = self.project.pdf_document
            
            # Check if file exists
            if not pdf_document.file or not pdf_document.file.name:
                logger.warning("PDF file not accessible, returning generated report only")
                self.buffer.seek(0)
                return self.buffer
            
            # Create PDF writer
            pdf_writer = PdfWriter()
            cad_pages_added = 0
            
            # Try to add original CAD pages
            try:
                logger.info(f"Opening CAD PDF: {pdf_document.file.name}")
                with pdf_document.file.open('rb') as cad_file:
                    cad_reader = PdfReader(cad_file)
                    num_cad_pages = len(cad_reader.pages)
                    logger.info(f"CAD PDF has {num_cad_pages} pages")
                    
                    if num_cad_pages == 0:
                        logger.warning("CAD PDF has 0 pages")
                    else:
                        for i in range(num_cad_pages):
                            try:
                                page = cad_reader.pages[i]
                                pdf_writer.add_page(page)
                                cad_pages_added += 1
                                logger.debug(f"Added CAD page {i+1}/{num_cad_pages}")
                            except Exception as e:
                                logger.error(f"Failed to add CAD page {i+1}: {e}")
                        
                        logger.info(f"Successfully added {cad_pages_added} CAD pages")
                        
            except FileNotFoundError:
                logger.error(f"CAD PDF file not found: {pdf_document.file.name}")
            except Exception as e:
                logger.error(f"Error reading CAD PDF: {e}\n{traceback.format_exc()}")
            
            # Add generated report pages
            try:
                self.buffer.seek(0)
                report_reader = PdfReader(self.buffer)
                num_report_pages = len(report_reader.pages)
                logger.info(f"Generated report has {num_report_pages} pages")
                
                report_pages_added = 0
                for i in range(num_report_pages):
                    try:
                        page = report_reader.pages[i]
                        pdf_writer.add_page(page)
                        report_pages_added += 1
                        logger.debug(f"Added report page {i+1}/{num_report_pages}")
                    except Exception as e:
                        logger.error(f"Failed to add report page {i+1}: {e}")
                
                logger.info(f"Successfully added {report_pages_added} report pages")
                
            except Exception as e:
                logger.error(f"Error reading generated report: {e}\n{traceback.format_exc()}")
                # If we can't even read our own report, something is very wrong
                raise
            
            # Write final merged PDF
            if len(pdf_writer.pages) == 0:
                logger.error("No pages were added to final PDF!")
                # Return just the generated report
                self.buffer.seek(0)
                return self.buffer
            
            final_buffer = BytesIO()
            pdf_writer.write(final_buffer)
            final_buffer.seek(0)
            
            logger.info(f"Final merged PDF created with {len(pdf_writer.pages)} total pages")
            return final_buffer
            
        except Exception as e:
            logger.error(f"Critical error in _merge_with_original_cad: {e}\n{traceback.format_exc()}")
            # Return just the generated report as fallback
            self.buffer.seek(0)
            return self.buffer
    
    def _add_cover_page(self):
        """Add professional cover page"""
        try:
            title = Paragraph(
                f"Design Proposal<br/>{self.project.name}",
                self.styles['CustomTitle']
            )
            self.story.append(Spacer(1, 1.5*inch))
            self.story.append(title)
            self.story.append(Spacer(1, 0.5*inch))
            
            details = [
                f"<b>Project Type:</b> {self.project.get_project_type_display()}",
                f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}",
                f"<b>Prepared for:</b> {self.project.created_by.get_full_name() or self.project.created_by.username}"
            ]
            
            for detail in details:
                p = Paragraph(detail, self.styles['Normal'])
                self.story.append(p)
                self.story.append(Spacer(1, 0.2*inch))
            
            if hasattr(settings, 'COMPANY_NAME'):
                self.story.append(Spacer(1, 2*inch))
                company = Paragraph(f"<b>{settings.COMPANY_NAME}</b>", self.styles['Normal'])
                self.story.append(company)
            
            self.story.append(PageBreak())
            logger.debug("Cover page added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_cover_page: {e}\n{traceback.format_exc()}")
            raise
    
    def _add_project_overview(self):
        """Add project overview section"""
        try:
            header = Paragraph("Project Overview", self.styles['SectionHeader'])
            self.story.append(header)
            
            overview_text = f"""
            This design proposal presents a comprehensive {self.project.get_project_type_display().lower()} 
            design with detailed specifications, photorealistic renderings, and itemized pricing.
            """
            
            p = Paragraph(overview_text, self.styles['Normal'])
            self.story.append(p)
            self.story.append(Spacer(1, 0.3*inch))
            
            # Statistics
            pdf_doc = self.project.pdf_document if hasattr(self.project, 'pdf_document') else None
            extractions = pdf_doc.pages.count() if pdf_doc else 0
            sku_matches = 0
            if hasattr(self.project, 'pricing') and self.project.pricing:
                sku_matches = self.project.pricing.items.count()
            
            stats_data = [
                ['Pages Analyzed', str(extractions)],
                ['Components Identified', str(sku_matches)],
                ['Renderings Generated', str(self.project.renders.filter(status='completed', is_active=True).count())]
            ]
            
            stats_table = Table(stats_data, colWidths=[3*inch, 1.5*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            
            self.story.append(stats_table)
            self.story.append(Spacer(1, 0.5*inch))
            self.story.append(PageBreak())
            logger.debug("Project overview added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_project_overview: {e}\n{traceback.format_exc()}")
            raise
    
    def _add_renders_section(self):
        """Add photorealistic renders"""
        try:
            header = Paragraph("Design Renderings", self.styles['SectionHeader'])
            self.story.append(header)
            
            renders = Render.objects.filter(
                project=self.project,
                status='completed',
                is_active=True
            ).select_related('pdf_page').order_by('pdf_page__page_number')
            
            logger.info(f"Found {renders.count()} renders to add")
            
            if not renders.exists():
                p = Paragraph("No completed renderings available.", self.styles['Normal'])
                self.story.append(p)
                return
            
            for render in renders:
                try:
                    title = Paragraph(
                        f"View {render.pdf_page.page_number} - {render.style_preference.title()} Style",
                        self.styles['Subsection']
                    )
                    self.story.append(title)
                    
                    if render.image_file:
                        try:
                            with render.image_file.open('rb') as f:
                                img_data = f.read()
                                img = Image.open(BytesIO(img_data))
                                
                                max_width = 6.5 * inch
                                max_height = 4.5 * inch
                                
                                img_width, img_height = img.size
                                aspect = img_height / img_width
                                
                                if img_width > max_width:
                                    img_width = max_width
                                    img_height = img_width * aspect
                                
                                if img_height > max_height:
                                    img_height = max_height
                                    img_width = img_height / aspect
                                
                                rl_img = RLImage(BytesIO(img_data), width=img_width, height=img_height)
                                self.story.append(rl_img)
                                self.story.append(Spacer(1, 0.2*inch))
                                logger.debug(f"Added render image for page {render.pdf_page.page_number}")
                                
                        except Exception as e:
                            logger.error(f"Failed to add render image: {e}")
                            p = Paragraph("Image unavailable", self.styles['Normal'])
                            self.story.append(p)
                    
                    desc = Paragraph(
                        f"Generated in {render.generation_time:.1f} seconds using AI rendering technology.",
                        self.styles['Normal']
                    )
                    self.story.append(desc)
                    self.story.append(Spacer(1, 0.3*inch))
                    
                    if render != renders.last():
                        self.story.append(PageBreak())
                        
                except Exception as e:
                    logger.error(f"Error adding render {render.id}: {e}")
                    continue
            
            self.story.append(PageBreak())
            logger.debug("Renders section added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_renders_section: {e}\n{traceback.format_exc()}")
            raise
    
    def _add_specifications_section(self):
        """Add detailed specifications with SKU images"""
        try:
            header = Paragraph("Product Specifications", self.styles['SectionHeader'])
            self.story.append(header)
            
            if not hasattr(self.project, 'pricing') or not self.project.pricing:
                logger.info("No pricing found, skipping specifications")
                p = Paragraph("No specifications available.", self.styles['Normal'])
                self.story.append(p)
                return
            
            line_items = self.project.pricing.items.select_related('sku_match__matched_sku').all()
            logger.info(f"Found {line_items.count()} line items")
            
            if not line_items.exists():
                p = Paragraph("No components specified.", self.styles['Normal'])
                self.story.append(p)
                return
            
            # Group by category
            categories = {}
            for item in line_items:
                if item.sku_match and item.sku_match.matched_sku:
                    sku = item.sku_match.matched_sku
                    category = sku.category
                    if category not in categories:
                        categories[category] = []
                    categories[category].append((item, sku))
            
            logger.info(f"Grouped into {len(categories)} categories: {list(categories.keys())}")
            
            if not categories:
                p = Paragraph("No matched SKU specifications available.", self.styles['Normal'])
                self.story.append(p)
                return
            
            # Create specifications for each category
            for category, items in categories.items():
                try:
                    subheader = Paragraph(f"{category.title()}s", self.styles['Subsection'])
                    self.story.append(subheader)
                    
                    for item, sku in items:
                        try:
                            # Safe dimension handling
                            width_str = f'{sku.width}"' if sku.width else 'N/A'
                            height_str = f'{sku.height}"' if sku.height else 'N/A'
                            depth_str = f'{sku.depth}"' if sku.depth else 'N/A'
                            
                            sku_details = f"""
                            <b>{sku.code}</b> - {sku.name}<br/>
                            <b>Dimensions:</b> {width_str}W × {height_str}H × {depth_str}D<br/>
                            <b>Finish:</b> {sku.finish or 'Standard'}<br/>
                            <b>Quantity:</b> {item.quantity}<br/>
                            <b>Unit Price:</b> ${item.unit_price}
                            """
                            
                            detail_cell = Paragraph(sku_details, self.styles['Normal'])
                            
                            # Try to add SKU image
                            table_data = []
                            if sku.image:
                                try:
                                    with sku.image.open('rb') as f:
                                        img_data = f.read()
                                        img = Image.open(BytesIO(img_data))
                                        
                                        max_size = 1.5 * inch
                                        img_width, img_height = img.size
                                        aspect = img_height / img_width
                                        
                                        if img_width > max_size:
                                            img_width = max_size
                                            img_height = img_width * aspect
                                        
                                        sku_image = RLImage(BytesIO(img_data), width=img_width, height=img_height)
                                        table_data.append([sku_image, detail_cell])
                                except Exception as e:
                                    logger.error(f"Failed to load SKU image for {sku.code}: {e}")
                                    table_data.append(['[No Image]', detail_cell])
                            else:
                                table_data.append(['[No Image]', detail_cell])
                            
                            sku_table = Table(table_data, colWidths=[2*inch, 4.5*inch])
                            sku_table.setStyle(TableStyle([
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                                ('PADDING', (0, 0), (-1, -1), 8)
                            ]))
                            
                            self.story.append(sku_table)
                            self.story.append(Spacer(1, 0.2*inch))
                            
                        except Exception as e:
                            logger.error(f"Error adding SKU {sku.code}: {e}")
                            continue
                    
                    self.story.append(Spacer(1, 0.3*inch))
                    
                except Exception as e:
                    logger.error(f"Error processing category {category}: {e}")
                    continue
            
            self.story.append(PageBreak())
            logger.debug("Specifications section added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_specifications_section: {e}\n{traceback.format_exc()}")
            raise
    
    def _add_pricing_section(self):
        """Add detailed pricing breakdown - FIXED with safer table styling"""
        try:
            header = Paragraph("Pricing Summary", self.styles['SectionHeader'])
            self.story.append(header)
            
            if not hasattr(self.project, 'pricing') or not self.project.pricing:
                p = Paragraph("Pricing not available.", self.styles['Normal'])
                self.story.append(p)
                return
            
            pricing = self.project.pricing
            line_items = pricing.items.all()
            
            logger.info(f"Adding pricing table with {line_items.count()} items")

            table_data = [['Item', 'SKU', 'Qty', 'Unit Price', 'Total']]
            
            for item in line_items:
                table_data.append([
                    item.sku_name[:40] + '...' if len(item.sku_name) > 40 else item.sku_name,
                    item.sku_code,
                    str(item.quantity),
                    f"${item.unit_price}",
                    f"${item.final_price}"
                ])
            
            # Remember where items end
            items_end_row = len(table_data)
            
            # Add totals
            table_data.append(['', '', '', '', ''])  # Blank row
            table_data.append(['', '', '', 'Subtotal:', f"${pricing.subtotal}"])
            
            if pricing.total_discount and pricing.total_discount > 0:
                table_data.append(['', '', '', 'Discount:', f"-${pricing.total_discount}"])
            
            if pricing.tax_amount and pricing.tax_amount > 0:
                table_data.append(['', '', '', f'Tax ({pricing.tax_rate}%):', f"${pricing.tax_amount}"])
            
            table_data.append(['', '', '', 'TOTAL:', f"${pricing.total}"])
            
            total_rows = len(table_data)
            logger.info(f"Pricing table has {total_rows} rows (items: {items_end_row - 1})")
            
            # Build table with SAFE indexing
            pricing_table = Table(table_data, colWidths=[2.5*inch, 1*inch, 0.5*inch, 1.2*inch, 1*inch])
            
            # Apply styles with calculated safe indices
            style_commands = [
                # Header row (row 0)
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                
                # All data alignment
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]
            
            # Only add item-specific styles if we have items
            if items_end_row > 1:
                style_commands.extend([
                    ('FONTSIZE', (0, 1), (-1, items_end_row-1), 9),
                    ('GRID', (0, 0), (-1, items_end_row-1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, items_end_row-1), [colors.white, colors.HexColor('#f8f9fa')]),
                ])
            
            # Totals section styling (last few rows)
            if total_rows > items_end_row + 1:
                style_commands.extend([
                    ('LINEABOVE', (3, items_end_row+1), (-1, items_end_row+1), 1, colors.black),
                    ('FONTNAME', (3, items_end_row+1), (-1, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (3, items_end_row+1), (-1, -1), 11),
                    ('BACKGROUND', (3, -1), (-1, -1), colors.HexColor('#27ae60')),
                    ('TEXTCOLOR', (3, -1), (-1, -1), colors.whitesmoke),
                ])
            
            pricing_table.setStyle(TableStyle(style_commands))
            
            self.story.append(pricing_table)
            self.story.append(Spacer(1, 0.5*inch))
            
            notes = Paragraph(
                "<b>Payment Terms:</b> 50% deposit required, balance due upon completion. "
                "Prices valid for 30 days from proposal date.",
                self.styles['Normal']
            )
            self.story.append(notes)
            self.story.append(PageBreak())
            logger.debug("Pricing section added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_pricing_section: {e}\n{traceback.format_exc()}")
            raise
    
    def _add_annotations_section(self):
        """Add annotations and special notes"""
        try:
            annotations = Annotation.objects.filter(
                render__project=self.project
            ).select_related('render__pdf_page').order_by('render__pdf_page__page_number', 'created_at')
            
            logger.info(f"Found {annotations.count()} annotations")
            
            if not annotations.exists():
                logger.debug("No annotations, skipping section")
                return
            
            header = Paragraph("Special Notes & Annotations", self.styles['SectionHeader'])
            self.story.append(header)
            
            intro = Paragraph(
                "The following notes and special requirements have been added to this project:",
                self.styles['Normal']
            )
            self.story.append(intro)
            self.story.append(Spacer(1, 0.3*inch))
            
            # Group by type
            special_cabinets = [a for a in annotations if a.annotation_type == 'special_cabinet']
            comments = [a for a in annotations if a.annotation_type == 'comment']
            change_requests = [a for a in annotations if a.annotation_type == 'change_request']
            
            for section_title, annotation_list in [
                ("Special Cabinet Requirements", special_cabinets),
                ("General Comments", comments),
                ("Change Requests", change_requests)
            ]:
                if annotation_list:
                    sub = Paragraph(section_title, self.styles['Subsection'])
                    self.story.append(sub)
                    
                    for annotation in annotation_list:
                        text = f"""
                        <b>Page {annotation.render.pdf_page.page_number}</b>
                        {f' - SKU: {annotation.sku_code}' if annotation.sku_code else ''}<br/>
                        {annotation.text}<br/>
                        <i>Added by: {annotation.created_by.username} on {annotation.created_at.strftime('%B %d, %Y')}</i>
                        """
                        p = Paragraph(text, self.styles['Normal'])
                        self.story.append(p)
                        self.story.append(Spacer(1, 0.2*inch))
            
            self.story.append(PageBreak())
            logger.debug("Annotations section added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_annotations_section: {e}\n{traceback.format_exc()}")
            # Don't raise - annotations are optional
    
    def _add_footer_info(self):
        """Add footer with contact information"""
        try:
            self.story.append(Spacer(1, 0.5*inch))
            
            footer_text = f"""
            <para align="center">
            <b>Thank you for considering our design proposal.</b><br/>
            For questions or modifications, please contact us.<br/><br/>
            Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}<br/>
            Project ID: {self.project.id}
            </para>
            """
            
            footer = Paragraph(footer_text, self.styles['Normal'])
            self.story.append(footer)
            logger.debug("Footer added successfully")
            
        except Exception as e:
            logger.error(f"Error in _add_footer_info: {e}\n{traceback.format_exc()}")
            # Don't raise - footer is optional


def generate_project_pdf(project: Project) -> BytesIO:
    """
    Helper function to generate complete PDF report
    
    Args:
        project: Project object
    
    Returns:
        BytesIO buffer with complete PDF (CAD pages + report)
    """
    try:
        generator = PDFReportGenerator(project)
        return generator.generate_complete_report()
    except Exception as e:
        logger.error(f"Failed to generate PDF for project {project.id}: {e}\n{traceback.format_exc()}")
        raise