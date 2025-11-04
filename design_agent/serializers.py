from rest_framework import serializers
from .models import (
    Project, PDFDocument, PDFPage, Extraction, 
    SKUCatalog, SKUMatch, Render
)

class ProjectSerializer(serializers.ModelSerializer):
    """Basic project serialization"""
    
    class Meta:
        model = Project
        fields = ['id', 'name', 'project_type', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class PDFDocumentSerializer(serializers.ModelSerializer):
    """PDF document serialization"""
    
    class Meta:
        model = PDFDocument
        fields = ['id', 'filename', 'page_count', 'processing_status', 'uploaded_at']
        read_only_fields = ['id', 'page_count', 'processing_status', 'uploaded_at']

class ExtractionSerializer(serializers.ModelSerializer):
    """Extraction data serialization"""
    page_number = serializers.IntegerField(source='pdf_page.page_number', read_only=True)
    
    class Meta:
        model = Extraction
        fields = ['id', 'page_number', 'structured_data', 'extraction_method', 'extracted_at']
        read_only_fields = ['id', 'extraction_method', 'extracted_at']

class SKUCatalogSerializer(serializers.ModelSerializer):
    """SKU catalog serialization"""
    
    class Meta:
        model = SKUCatalog
        fields = [
            'id', 'code', 'name', 'category', 'subcategory',
            'width', 'height', 'depth', 
            'style', 'finish', 'material',
            'image', 'description'
        ]
        read_only_fields = ['id']

class SKUMatchSerializer(serializers.ModelSerializer):
    """SKU match serialization"""
    matched_sku_detail = SKUCatalogSerializer(source='matched_sku', read_only=True)
    
    class Meta:
        model = SKUMatch
        fields = [
            'id', 'label_text', 'label_category', 
            'matched_sku', 'matched_sku_detail',
            'match_score', 'position_data', 'alternative_skus',
            'matched_at'
        ]
        read_only_fields = ['id', 'matched_at']

class RenderSerializer(serializers.ModelSerializer):
    """Render serialization"""
    page_number = serializers.IntegerField(source='pdf_page.page_number', read_only=True)
    
    class Meta:
        model = Render
        fields = [
            'id', 'page_number', 'style_preference', 
            'image_file', 'generation_time', 
            'status', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'generation_time', 'status', 'created_at']