from .models import (
    SKUCatalog, Project, PDFDocument, PDFPage,
    Extraction, SKUMatch, Render, Pricing, PricingLineItem
)
from django.contrib import admin


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'project_type', 'created_by', 'created_at', 'is_active')
    search_fields = ('name', 'created_by__username')
    list_filter = ('project_type', 'is_active')
    ordering = ('-created_at',)


@admin.register(PDFDocument)
class PDFDocumentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'project', 'page_count', 'processing_status', 'uploaded_at')
    list_filter = ('processing_status',)
    search_fields = ('filename', 'project__name')


@admin.register(PDFPage)
class PDFPageAdmin(admin.ModelAdmin):
    list_display = ('pdf_document', 'page_number', 'width', 'height', 'dpi')
    list_filter = ('pdf_document',)
    ordering = ('pdf_document', 'page_number')


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ('pdf_page', 'status', 'extraction_method', 'extracted_at')
    list_filter = ('status', 'extraction_method')
    search_fields = ('pdf_page__pdf_document__filename',)
    readonly_fields = ('structured_data',)


@admin.register(SKUCatalog)
class SKUCatalogAdmin(admin.ModelAdmin):
    list_display = ('code','id', 'name', 'category', 'image', 'price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name', 'image', 'style', 'finish')
    ordering = ('category', 'code')


@admin.register(SKUMatch)
class SKUMatchAdmin(admin.ModelAdmin):
    list_display = ('label_text', 'label_category', 'matched_sku', 'match_score', 'extraction', 'matched_at')
    list_filter = ('label_category',)
    search_fields = ('label_text', 'matched_sku__code')


@admin.register(Render)
class RenderAdmin(admin.ModelAdmin):
    list_display = ('project', 'pdf_page', 'style_preference', 'status', 'generation_time', 'created_at')
    list_filter = ('status', 'style_preference')
    search_fields = ('project__name',)
    ordering = ('-created_at',)


@admin.register(Pricing)
class PricingAdmin(admin.ModelAdmin):
    list_display = ('project', 'subtotal', 'tax_amount', 'total', 'status', 'updated_at')
    list_filter = ('status',)
    search_fields = ('project__name',)
    readonly_fields = ('subtotal', 'total_discount', 'tax_amount', 'total')


@admin.register(PricingLineItem)
class PricingLineItemAdmin(admin.ModelAdmin):
    list_display = (
        'pricing', 'sku_code', 'sku_name', 'quantity',
        'unit_price', 'discount_percentage', 'final_price', 'is_optional'
    )
    list_filter = ('is_optional',)
    search_fields = ('sku_code', 'sku_name', 'pricing__project__name')
    ordering = ('pricing', 'sku_code')
