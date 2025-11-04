# design_agent/pricing_views.py
"""
FIXED Pricing Management APIs
"""

import logging
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, SKUMatch, Pricing, PricingLineItem, Extraction

logger = logging.getLogger('design_agent')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_pricing(request, project_id):
    """
    POST /api/projects/{id}/pricing/generate/
    
    Generate pricing from ALL extracted items (matched + unmatched)
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)

        if not hasattr(project, 'pdf_document'):
            return Response(
                {'error': 'No PDF uploaded'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        pdf_document = project.pdf_document

        # Get all extractions
        extractions = Extraction.objects.filter(
            pdf_page__pdf_document=pdf_document,
            status='completed'
        ).prefetch_related('sku_matches__matched_sku').order_by('pdf_page__page_number')

        if not extractions.exists():
            return Response(
                {'error': 'No extractions found. Run extract_layout first.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Collect ALL items from extractions
        all_items = []
        for extraction in extractions:
            items = extraction.structured_data.get('items', [])
            for item in items:
                all_items.append({
                    'extraction': extraction,
                    'label': item.get('label', '').strip(),
                    'category': item.get('category', ''),
                    'dimensions': item.get('dimensions', {}),
                    'page_number': extraction.pdf_page.page_number
                })

        if not all_items:
            return Response(
                {'error': 'No items found in extractions'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"💰 Generating pricing for {len(all_items)} extracted items")

        # Get all existing SKU matches for quick lookup
        sku_matches_dict = {}
        for extraction in extractions:
            for match in extraction.sku_matches.all():
                sku_matches_dict[f"{extraction.id}_{match.label_text}"] = match

        # Delete old pricing if exists
        Pricing.objects.filter(project=project).delete()

        # Create new pricing
        pricing = Pricing.objects.create(
            project=project, 
            status='draft',
            subtotal=Decimal('0.00'),
            total=Decimal('0.00')
        )

        total = Decimal('0.00')
        items_data = []
        matched_count = 0
        unmatched_count = 0
        skus_without_price = []

        # Process EACH extracted item
        for item_info in all_items:
            extraction = item_info['extraction']
            label = item_info['label']
            page_number = item_info['page_number']
            
            if not label:
                logger.warning(f"   ⚠️ Empty label on page {page_number}, skipping")
                continue

            # Check if this item has a SKU match
            match_key = f"{extraction.id}_{label}"
            sku_match = sku_matches_dict.get(match_key)

            if sku_match and sku_match.matched_sku:
                # MATCHED SKU - use catalog data
                sku = sku_match.matched_sku
                sku_code = sku.code
                sku_name = sku.name
                
                if sku.price is not None:
                    unit_price = Decimal(str(sku.price))
                else:
                    unit_price = Decimal('0.00')
                    skus_without_price.append({
                        'sku_code': sku_code,
                        'sku_name': sku_name,
                        'page': page_number
                    })
                
                matched_count += 1
                is_matched = True
                
            else:
                # UNMATCHED SKU - use label as code
                sku_code = label
                sku_name = f"{label} (Unmatched)"
                unit_price = Decimal('0.00')
                sku_match = None
                unmatched_count += 1
                is_matched = False

            quantity = 1
            line_total = unit_price * quantity

            # Create pricing line item
            line_item = PricingLineItem.objects.create(
                pricing=pricing,
                sku_match=sku_match,
                sku_code=sku_code,
                sku_name=sku_name,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=line_total,
                discount_percentage=0,
                discount_amount=0,
                final_price=line_total,
                notes="Unmatched - needs manual pricing" if not is_matched else None
            )

            total += line_total
            
            items_data.append({
                'id': str(line_item.id),
                'page': page_number,
                'sku_code': sku_code,
                'sku_name': sku_name,
                'quantity': quantity,
                'unit_price': str(unit_price),
                'line_total': str(line_total),
                'is_matched': is_matched,
                'has_price': unit_price > 0
            })

            status_emoji = "✅" if is_matched else "❌"
            logger.info(f"   {status_emoji} {sku_code} - ${unit_price} (page {page_number})")

        # Save total
        pricing.subtotal = total
        pricing.total = total
        pricing.save()

        logger.info(f"✅ Pricing generated: {len(items_data)} items ({matched_count} matched, {unmatched_count} unmatched), Total: ${total}")

        response_data = {
            'project_id': str(project.id),
            'pricing_id': str(pricing.id),
            'total_items': len(items_data),
            'matched_items': matched_count,
            'unmatched_items': unmatched_count,
            'subtotal': str(pricing.subtotal),
            'total': str(total),
            'items': items_data
        }

        # Add warnings
        warnings = []
        if unmatched_count > 0:
            warnings.append(f"{unmatched_count} items are unmatched and need manual pricing")
        if skus_without_price:
            warnings.append(f"{len(skus_without_price)} matched SKUs have no price in catalog")
        
        if warnings:
            response_data['warnings'] = warnings
            response_data['unmatched_details'] = [
                item for item in items_data if not item['is_matched']
            ]
            response_data['skus_without_price'] = skus_without_price

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error generating pricing: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pricing(request, project_id):
    """
    GET /api/projects/{id}/pricing/
    
    Get complete pricing breakdown
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()

        if not pricing:
            return Response(
                {'error': 'No pricing found. Run generate_pricing first.'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        items = pricing.items.select_related('sku_match__extraction__pdf_page').order_by(
            'sku_match__extraction__pdf_page__page_number'
        )
        
        items_data = []
        for item in items:
            page_num = item.sku_match.extraction.pdf_page.page_number if item.sku_match else None
            
            items_data.append({
                'id': str(item.id),
                'page': page_num,
                'sku_code': item.sku_code,
                'sku_name': item.sku_name,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
                'discount': str(item.discount_amount) if item.discount_amount else None,
                'line_total': str(item.final_price),
                'notes': item.notes
            })

        return Response({
            'pricing_id': str(pricing.id),
            'status': pricing.status,
            'total_items': len(items_data),
            'subtotal': str(pricing.subtotal),
            'discount': str(pricing.total_discount) if pricing.total_discount else None,
            'tax': str(pricing.tax_amount) if pricing.tax_amount else None,
            'total': str(pricing.total),
            'is_locked': pricing.status == 'locked',
            'items': items_data
        }, status=status.HTTP_200_OK)

    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error fetching pricing: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_pricing_item(request, project_id, item_id):
    """
    PUT /api/projects/{id}/pricing/items/{item_id}/
    
    Update individual pricing item (quantity, price, discount, notes)
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status == 'locked':
            return Response(
                {'error': 'Pricing is locked. Unlock it first to make changes.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # FIXED: Use get() with proper error handling
        try:
            pricing_item = PricingLineItem.objects.get(id=item_id, pricing=pricing)
        except PricingLineItem.DoesNotExist:
            # Log available items for debugging
            available_items = PricingLineItem.objects.filter(pricing=pricing).values_list('id', flat=True)
            logger.error(f"Item {item_id} not found. Available items: {list(available_items)}")
            return Response(
                {
                    'error': f'Pricing item {item_id} not found for this project',
                    'available_items': list(available_items)
                }, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Track what changed
        changes = {}
        
        # Update quantity
        if 'quantity' in request.data:
            quantity = int(request.data['quantity'])
            if quantity < 1:
                return Response(
                    {'error': 'Quantity must be at least 1'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            pricing_item.quantity = quantity
            changes['quantity'] = quantity
        
        # Update unit price
        if 'unit_price' in request.data:
            unit_price = Decimal(str(request.data['unit_price']))
            if unit_price < 0:
                return Response(
                    {'error': 'Unit price cannot be negative'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            pricing_item.unit_price = unit_price
            changes['unit_price'] = str(unit_price)
        
        # Update discount
        if 'discount_percentage' in request.data:
            discount = Decimal(str(request.data['discount_percentage']))
            if discount < 0 or discount > 100:
                return Response(
                    {'error': 'Discount must be between 0 and 100'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            pricing_item.discount_percentage = discount
            changes['discount_percentage'] = str(discount)
        
        # Update notes
        if 'notes' in request.data:
            pricing_item.notes = request.data['notes']
            changes['notes'] = request.data['notes']
        
        # Recalculate line item totals
        subtotal = pricing_item.unit_price * pricing_item.quantity
        pricing_item.subtotal = subtotal
        
        if pricing_item.discount_percentage:
            discount_amount = subtotal * (pricing_item.discount_percentage / 100)
            pricing_item.discount_amount = discount_amount
            pricing_item.final_price = subtotal - discount_amount
        else:
            pricing_item.discount_amount = Decimal('0.00')
            pricing_item.final_price = subtotal
        
        pricing_item.save()
        
        # Recalculate project totals
        pricing.calculate_totals()
        pricing.save()
        
        logger.info(f"✅ Updated pricing item {item_id}: {changes}")
        
        # FIXED: Use final_price instead of line_total
        return Response({
            'item_id': str(pricing_item.id),
            'changes': changes,
            'new_line_total': str(pricing_item.final_price),  # FIXED: was line_total
            'project_subtotal': str(pricing.subtotal),
            'project_total': str(pricing.total),
            'message': 'Pricing item updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return Response(
            {'error': f'Invalid value: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"❌ Error updating pricing item: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_project_pricing(request, project_id):
    """
    PUT /api/projects/{id}/pricing/
    
    Update project-level pricing (tax rate, overall discount, notes)
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status == 'locked':
            return Response(
                {'error': 'Pricing is locked. Unlock it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        changes = {}
        
        # Update tax rate
        if 'tax_rate' in request.data:
            tax_rate = Decimal(str(request.data['tax_rate']))
            if tax_rate < 0 or tax_rate > 100:
                return Response(
                    {'error': 'Tax rate must be between 0 and 100'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            pricing.tax_rate = tax_rate
            changes['tax_rate'] = str(tax_rate)
        
        # Update overall discount
        if 'overall_discount_percentage' in request.data:
            discount = Decimal(str(request.data['overall_discount_percentage']))
            if discount < 0 or discount > 100:
                return Response(
                    {'error': 'Overall discount must be between 0 and 100'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            changes['overall_discount'] = str(discount)
        
        # Recalculate totals
        pricing.calculate_totals()
        pricing.save()
        
        logger.info(f"✅ Updated project pricing: {changes}")
        
        return Response({
            'pricing_id': str(pricing.id),
            'changes': changes,
            'new_subtotal': str(pricing.subtotal),
            'new_total': str(pricing.total),
            'message': 'Project pricing updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error updating project pricing: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_pricing_item(request, project_id, item_id):
    """
    DELETE /api/projects/{id}/pricing/items/{item_id}/
    
    Delete a pricing line item
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status == 'locked':
            return Response(
                {'error': 'Pricing is locked. Unlock it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = PricingLineItem.objects.get(id=item_id, pricing=pricing)
        except PricingLineItem.DoesNotExist:
            return Response(
                {'error': f'Pricing item {item_id} not found for this project'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        sku_code = item.sku_code
        
        item.delete()
        
        # Recalculate totals
        pricing.calculate_totals()
        pricing.save()
        
        logger.info(f"🗑️ Deleted pricing item {item_id} ({sku_code})")
        
        return Response({
            'message': f'Item {sku_code} deleted successfully',
            'new_total': str(pricing.total)
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error deleting pricing item: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_custom_item(request, project_id):
    """
    POST /api/projects/{id}/pricing/items/
    
    Add custom pricing item
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found. Generate pricing first.'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status == 'locked':
            return Response(
                {'error': 'Pricing is locked. Unlock it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate required fields
        sku_code = request.data.get('sku_code')
        sku_name = request.data.get('sku_name')
        quantity = request.data.get('quantity', 1)
        unit_price = request.data.get('unit_price', 0)
        
        if not sku_code or not sku_name:
            return Response(
                {'error': 'sku_code and sku_name are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        quantity = int(quantity)
        unit_price = Decimal(str(unit_price))
        line_total = quantity * unit_price
        
        # Create custom item
        item = PricingLineItem.objects.create(
            pricing=pricing,
            sku_match=None,
            sku_code=sku_code,
            sku_name=sku_name,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=line_total,
            final_price=line_total,
            notes=request.data.get('notes', 'Custom item')
        )
        
        # Recalculate totals
        pricing.calculate_totals()
        pricing.save()
        
        logger.info(f"➕ Added custom item: {sku_code} - ${unit_price}")
        
        return Response({
            'item_id': str(item.id),
            'sku_code': item.sku_code,
            'sku_name': item.sku_name,
            'quantity': item.quantity,
            'unit_price': str(item.unit_price),
            'line_total': str(item.final_price),
            'new_total': str(pricing.total),
            'message': 'Custom item added successfully'
        }, status=status.HTTP_201_CREATED)
        
    except ValueError as e:
        return Response(
            {'error': f'Invalid value: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"❌ Error adding custom item: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def lock_pricing(request, project_id):
    """
    POST /api/projects/{id}/pricing/lock/
    
    Lock pricing (prevents further edits)
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status == 'locked':
            return Response(
                {'error': 'Pricing is already locked'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pricing.status = 'locked'
        pricing.save()
        
        logger.info(f"🔒 Locked pricing for project {project_id}")
        
        return Response({
            'pricing_id': str(pricing.id),
            'status': 'locked',
            'total': str(pricing.total),
            'message': 'Pricing locked successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error locking pricing: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unlock_pricing(request, project_id):
    """
    POST /api/projects/{id}/pricing/unlock/
    
    Unlock pricing (allow edits again)
    """
    try:
        project = Project.objects.get(id=project_id, created_by=request.user)
        pricing = Pricing.objects.filter(project=project).first()
        
        if not pricing:
            return Response(
                {'error': 'No pricing found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if pricing.status != 'locked':
            return Response(
                {'error': 'Pricing is not locked'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pricing.status = 'draft'
        pricing.save()
        
        logger.info(f"🔓 Unlocked pricing for project {project_id}")
        
        return Response({
            'pricing_id': str(pricing.id),
            'status': 'draft',
            'message': 'Pricing unlocked successfully'
        }, status=status.HTTP_200_OK)
        
    except Project.DoesNotExist:
        return Response(
            {'error': 'Project not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"❌ Error unlocking pricing: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )