from design_agent.models import SKUCatalog
from decimal import Decimal

# Clear existing test data if needed
# SKUCatalog.objects.all().delete()

# FIXED SKU data matching your extraction patterns
# Cedar SKUs (Kitchen & Bath)
cedar_skus = [
    ("TEP3096L", "Tall End Panel 30x96 Left", "cabinet", 30, 96, 0.75, "Left side tall end panel"),
    ("TEP3096R", "Tall End Panel 30x96 Right", "cabinet", 30, 96, 0.75, "Right side tall end panel"),
    ("P2490", "Pantry 24x90", "cabinet", 24, 90, 24, "Tall pantry cabinet 24x90"),
    ("LMXS28596S", "LG Refrigerator 36 French Door", "appliance", 36, 70, 30, "LG 28 cu.ft. French Door refrigerator"),
    ("DB18-3", "Drawer Base 18 Three Drawer", "cabinet", 18, 34.5, 24, "Three-drawer base cabinet 18 inches"),
    ("LSEL6337F", "LG Electric Range 30", "appliance", 30, 36, 25, "LG 30-inch electric range"),
    ("B09R", "Base Cabinet 9 Right", "cabinet", 9, 34.5, 24, "Narrow base cabinet right hinge"),
    ("ER36R", "Range Hood 36 Right", "appliance", 36, 18, 20, "36-inch range hood right"),
    ("HMV8053U", "Bosch Microwave 30 Over Range", "appliance", 30, 17, 15, "30-inch over-the-range microwave"),
    ("B12L", "Base Cabinet 12 Left", "cabinet", 12, 34.5, 24, "Base cabinet 12 inches left hinge"),
    ("SB36", "Sink Base 36", "cabinet", 36, 34.5, 24, "Sink base cabinet 36 inches wide"),
    ("SKSDW2411S", "SKS Dishwasher 24", "appliance", 24, 34.5, 24, "Signature Kitchen Suite dishwasher 24 inches"),
    ("B33", "Base Cabinet 33", "cabinet", 33, 34.5, 24, "Base cabinet 33 inches wide"),
    ("DWR3R", "Drawer Wall Right 3", "cabinet", 3, 30, 12, "Right side 3-inch wall drawer"),
    ("W1836L", "Wall Cabinet 18x36 Left", "cabinet", 18, 36, 12, "Wall cabinet 18x36 left hinge"),
    ("W1836R", "Wall Cabinet 18x36 Right", "cabinet", 18, 36, 12, "Wall cabinet 18x36 right hinge"),
    ("W3018", "Wall Cabinet 30x18", "cabinet", 30, 18, 12, "Wall cabinet 30x18x12"),
    ("W2136R", "Wall Cabinet 21x36 Right", "cabinet", 21, 36, 12, "Wall cabinet 21x36 right hinge"),
    ("W361824", "Wall Cabinet 36x18x24", "cabinet", 36, 18, 24, "Wide wall cabinet 36x18x24"),
    ("W3636", "Wall Cabinet 36x36", "cabinet", 36, 36, 12, "Wall cabinet 36x36x12"),
    ("CW2436L", "Corner Wall Cabinet 24x36 Left", "cabinet", 24, 36, 24, "Corner wall cabinet left hinge"),
    ("DWP1236R", "Dishwasher Panel 12x36 Right", "cabinet", 12, 36, 0.75, "Dishwasher decorative panel 12x36 right"),
]

print("Populating SKU catalog with FIXED data...")
print(f"Total SKUs to create: {len(cedar_skus)}\n")

created_count = 0
skipped_count = 0

for sku_data in cedar_skus:
    code, name, category, width, height, depth, description = sku_data
    
    # Check if SKU already exists
    if SKUCatalog.objects.filter(code=code).exists():
        print(f"⏭️  Skipped (exists): {code}")
        skipped_count += 1
        continue
    
    try:
        sku = SKUCatalog.objects.create(
            code=code,
            name=name,
            category=category,
            subcategory="",
            width=Decimal(str(width)) if width else None,
            height=Decimal(str(height)) if height else None,
            depth=Decimal(str(depth)) if depth else None,
            style="modern",
            finish="white",
            material="wood",
            description=description,
            is_active=True
        )
        print(f"✓ Created: {code} - {name}")
        created_count += 1
        
    except Exception as e:
        print(f"❌ Error creating {code}: {str(e)}")

print(f"\n{'='*60}")
print(f"Summary:")
print(f"  Created: {created_count}")
print(f"  Skipped: {skipped_count}")
print(f"  Total in DB: {SKUCatalog.objects.count()}")
print(f"{'='*60}\n")