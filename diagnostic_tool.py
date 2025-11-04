# diagnostic_tool.py
"""
Diagnostic tool to check extraction quality
Run this to see what Claude extracted vs what we expected
"""

import requests
import json
from collections import Counter


def analyze_extraction(project_id, base_url="http://localhost:8000"):
    """Analyze extraction results for a project"""
    
    # Login
    session = requests.Session()
    response = session.post(f"{base_url}/api/auth/login/", json={
        'username': 'test_bedrock',
        'password': 'test_pass_123'
    })
    
    if response.status_code != 200:
        print("❌ Login failed")
        return
    
    token = response.json()['token']
    session.headers.update({'Authorization': f'Token {token}'})
    
    # Get extraction results
    response = session.get(f"{base_url}/api/projects/{project_id}/extraction_results/")
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch extractions: {response.text}")
        return
    
    data = response.json()
    
    print("\n" + "="*80)
    print("🔍 EXTRACTION DIAGNOSTIC REPORT")
    print("="*80)
    print(f"Project ID: {project_id}")
    print(f"Total Pages: {data['total_pages']}\n")
    
    # Expected SKUs from 610_kitchen.pdf
    expected_page1 = {
        'BC242484-1TDL', 'OV302D84', 'FSEP24120', 'DISH-FIGE', 'SB42FH',
        'BTB24KSBFH', 'BC182484TDR', 'USF3102', 'BI-36U/O-RH', 'FL3102',
        'FLAT PNL 3/4', 'DB24', 'B15FHR', 'DB24-2D', 'USF330B', 'CKT.36',
        'W2130-15L', 'W4230-15', 'W2130-15R', 'WP2424-15HK', 'WP3024-15HK',
        'WP3624-15HK', 'WP1824-15HK', 'DOOR-NH', 'FLAT PNL 5/8'
    }
    
    for extraction in data['extractions']:
        page = extraction['page']
        items = extraction['items']
        view_type = extraction['view_type']
        
        print(f"{'='*80}")
        print(f"📄 PAGE {page} - {view_type.upper()}")
        print(f"{'='*80}")
        
        extracted_labels = [item['label'] for item in items if item.get('label')]
        
        print(f"\n📊 STATISTICS:")
        print(f"   Items extracted: {len(items)}")
        print(f"   Expected (Page 1): ~{len(expected_page1)} SKUs")
        
        if page == 1:
            matched = set(extracted_labels) & expected_page1
            missing = expected_page1 - set(extracted_labels)
            extra = set(extracted_labels) - expected_page1
            
            print(f"\n✅ Correctly Found: {len(matched)}/{len(expected_page1)} ({len(matched)/len(expected_page1)*100:.1f}%)")
            print(f"❌ Missing: {len(missing)}")
            print(f"➕ Extra: {len(extra)}")
        
        print(f"\n📦 ALL EXTRACTED ITEMS:")
        print("-"*80)
        
        for i, item in enumerate(items, 1):
            label = item.get('label', 'NO_LABEL')
            category = item.get('category', 'unknown')
            dims = item.get('dimensions', {})
            notes = item.get('notes', '')
            
            # Format dimensions
            dim_str = f"W:{dims.get('width', '?')}, H:{dims.get('height', '?')}, D:{dims.get('depth', '?')}"
            
            # Check if expected
            status = "✅" if (page == 1 and label in expected_page1) else "❓"
            
            print(f"{i:2}. {status} {label:20} | {category:15} | {dim_str:30} | {notes[:30]}")
        
        if page == 1 and missing:
            print(f"\n❌ MISSING SKUs (Should be on Page 1):")
            print("-"*80)
            for sku in sorted(missing)[:15]:
                print(f"   • {sku}")
            if len(missing) > 15:
                print(f"   ... and {len(missing) - 15} more")
    
    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS:")
    print("="*80)
    
    total_extracted = sum(len(e['items']) for e in data['extractions'])
    expected_total = len(expected_page1) + 20 + 6  # Page 1 + Page 2 + Page 3
    
    accuracy = (total_extracted / expected_total) * 100 if expected_total > 0 else 0
    
    if accuracy < 50:
        print("🔴 CRITICAL: Extraction is severely underperforming")
        print("   1. Check Celery logs for raw Claude response")
        print("   2. Image quality may be too low (increase DPI)")
        print("   3. Prompt may need refinement for your specific drawing style")
    elif accuracy < 75:
        print("🟡 WARNING: Extraction missing significant data")
        print("   1. Review extraction prompt for completeness")
        print("   2. Check if Claude is stopping early")
        print("   3. Consider increasing max_tokens in unified_extractor.py")
    else:
        print("✅ GOOD: Extraction quality is acceptable")
        print("   Minor improvements possible through prompt tuning")
    
    print("\n📝 NEXT STEPS:")
    print("   1. Check Celery worker logs for detailed extraction data")
    print("   2. Look for '📋 RAW EXTRACTION RESPONSE' in logs")
    print("   3. Verify if Claude is seeing all SKU codes in the image")
    print("="*80 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python diagnostic_tool.py <project_id>")
        print("\nExample:")
        print("  python diagnostic_tool.py de8c518f-6e7b-48cc-b97f-fd460d13a78a")
        sys.exit(1)
    
    project_id = sys.argv[1]
    analyze_extraction(project_id)