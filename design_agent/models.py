"""
Simplified models for MVP
Only essential fields for 25-35 SKUs
"""

from django.db import models
from django.contrib.auth.models import User
import uuid
from decimal import Decimal


class Annotation(models.Model):
    """
    Annotations for renders - special notes, comments, change requests
    """
    ANNOTATION_TYPES = [
        ('special_cabinet', 'Special Cabinet Note'),
        ('comment', 'General Comment'),
        ('change_request', 'Change Request'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    render = models.ForeignKey('Render', on_delete=models.CASCADE, related_name='annotations')
    annotation_type = models.CharField(max_length=20, choices=ANNOTATION_TYPES)
    text = models.TextField()
    sku_code = models.CharField(max_length=100, null=True, blank=True)  # If related to specific SKU
    position_x = models.IntegerField(null=True, blank=True)  # Optional positioning
    position_y = models.IntegerField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.annotation_type} - {self.render.project.name}"
    
    
class Project(models.Model):
    """Main project container"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    project_type = models.CharField(
        max_length=20,
        choices=[('kitchen', 'Kitchen'), ('bathroom', 'Bathroom')],
        default='kitchen'
    )
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='approved_projects'
    )
    notes = models.TextField(blank=True, default='')  # General project notes

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']


class PDFDocument(models.Model):
    """Uploaded PDF files"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='pdf_document')
    file = models.FileField(upload_to='pdfs/%Y/%m/')
    filename = models.CharField(max_length=255)
    page_count = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Processing status
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('uploaded', 'Uploaded'),
            ('converting', 'Converting to Images'),
            ('extracting', 'Extracting Data'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='uploaded'
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'pdf_documents'


class PDFPage(models.Model):
    """Individual pages from PDF (as images)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pdf_document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, related_name='pages')
    page_number = models.IntegerField()
    image_file = models.ImageField(upload_to='pdf_pages/%Y/%m/')
    width = models.IntegerField()  # pixels
    height = models.IntegerField()  # pixels
    dpi = models.IntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)
    preview_3d_image = models.ImageField(
        upload_to='3d_previews/%Y/%m/',
        blank=True,
        null=True,
        help_text='Simple 3D preview for layout validation before final render'
    )
    class Meta:
        db_table = 'pdf_pages'
        ordering = ['page_number']
        unique_together = ['pdf_document', 'page_number']


class Extraction(models.Model):
    """Extracted data from each PDF page"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pdf_page = models.OneToOneField(PDFPage, on_delete=models.CASCADE, related_name='extraction')
    
    # ADD THIS STATUS FIELD
    status = models.CharField(
        max_length=20,
        choices=[
            ('queued', 'Queued'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='queued'
    )
    
    structured_data = models.JSONField(default=dict)
    
    extraction_method = models.CharField(max_length=50, default='openai_gpt4_vision')
    raw_response = models.TextField(blank=True)
    extracted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'extractions'


class SKUCatalog(models.Model):
    """Product SKU catalog - only 25-35 items for MVP"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic info
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=50,
        choices=[
            ('cabinet', 'Cabinet'),
            ('tile', 'Tile'),
            ('appliance', 'Appliance')
        ],
        db_index=True
    )
    subcategory = models.CharField(max_length=100, blank=True)  # e.g., "base cabinet", "wall cabinet"
    
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    depth = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
    style = models.CharField(max_length=50, blank=True)  # modern, traditional, minimalist
    finish = models.CharField(max_length=50, blank=True)  # white, wood, stainless
    material = models.CharField(max_length=50, blank=True)
    
    image = models.ImageField(upload_to='sku_images/')
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Unit price in USD"
    )
    description = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sku_catalog'
        indexes = [
            models.Index(fields=['category', 'width', 'height']),
            models.Index(fields=['category', 'subcategory']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SKUMatch(models.Model):
    """Matched SKUs for each extracted label"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(Extraction, on_delete=models.CASCADE, related_name='sku_matches')
    
    label_text = models.CharField(max_length=100)  # e.g., "BC242484-1TDL"
    label_category = models.CharField(max_length=50)
    
    matched_sku = models.ForeignKey(SKUCatalog, on_delete=models.PROTECT)
    match_score = models.FloatField()  # 0-1 confidence score
    
    position_data = models.JSONField(default=dict)
    
    alternative_skus = models.JSONField(default=list)
    
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sku_matches'


class Render(models.Model):
    """Generated renders from Gemini"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='renders')
    pdf_page = models.ForeignKey(PDFPage, on_delete=models.CASCADE, related_name='renders')
    
    style_preference = models.CharField(max_length=50, default='modern')
    gemini_prompt = models.TextField()
    
    image_file = models.ImageField(upload_to='renders/%Y/%m/')
    
    generation_time = models.FloatField(default=0)  # seconds
    status = models.CharField(
        max_length=20,
        choices=[
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='processing'
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    parent_render = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='versions'
    )
    regeneration_reason = models.TextField(blank=True, default='')  # Why was it regenerated

    class Meta:
        db_table = 'renders'
        ordering = ['-version', '-created_at']        
        
class PricingLineItem(models.Model):
    pricing = models.ForeignKey(
        'Pricing',
        related_name='items',
        on_delete=models.CASCADE
    )
    sku_match = models.ForeignKey('SKUMatch', on_delete=models.SET_NULL, null=True, blank=True)
    sku_code = models.CharField(max_length=255)
    sku_name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    is_optional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['pricing', 'sku_code']
    
    def save(self, *args, **kwargs):
        self.subtotal = Decimal(str(self.quantity)) * self.unit_price
        self.discount_amount = (self.subtotal * self.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        self.final_price = self.subtotal - self.discount_amount
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.sku_code} × {self.quantity} = ${self.final_price}"


class Pricing(models.Model):
    """Overall project pricing summary"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('locked', 'Locked')
    ]
    
    project = models.OneToOneField(
        'Project',
        on_delete=models.CASCADE,
        related_name='pricing'
    )
    
    # Totals
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    total_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('8.50'),  
        help_text="Tax rate %"
    )
    
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Final total including tax"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_pricings'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def calculate_totals(self):
        """Recalculate all totals from line items"""
        line_items = self.items.all()
        
        self.subtotal = Decimal('0.00')
        for item in line_items:
            if item.unit_price:
                self.subtotal += item.final_price  # ✅ FIXED
        
        self.tax_amount = (self.subtotal * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        self.total = self.subtotal + self.tax_amount
        self.save() 
            
    
    def lock(self, user):
        """Lock pricing (prevent further changes)"""
        from django.utils import timezone
        self.status = 'locked'
        self.locked_at = timezone.now()
        self.locked_by = user
        self.save()
    
    def __str__(self):
        return f"Pricing for {self.project.name}: ${self.total}"
    
