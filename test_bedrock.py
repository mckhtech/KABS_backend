"""
Complete Pipeline Test with Bedrock
Tests: PDF → Bedrock Extraction → SKU Matching → Pricing → Rendering
"""

import requests
import time
import json
from pathlib import Path
from typing import Dict


class BedrockPipelineTester:
    """Test complete pipeline with Bedrock integration"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        self.session = requests.Session()
    
    def register_and_login(self, username="test_bedrock", password="test_pass_123", email="bedrock@test.com"):
        """Step 0: Authentication"""
        print("\n🔐 Step 0: Authentication")
        
        # Try login first
        response = self.session.post(f"{self.base_url}/api/auth/login/", json={
            'username': username,
            'password': password
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data['token']
            self.session.headers.update({'Authorization': f'Token {self.token}'})
            print(f"✅ Logged in as {username}")
            return data
        
        # If login fails, try registration
        response = self.session.post(f"{self.base_url}/api/auth/register/", json={
            'username': username,
            'password': password,
            'email': email
        })
        
        if response.status_code == 201:
            data = response.json()
            self.token = data['token']
            self.session.headers.update({'Authorization': f'Token {self.token}'})
            print(f"✅ Registered & logged in as {username}")
            return data
        else:
            print(f"❌ Auth failed: {response.text}")
            return None
    
    def create_project(self, name, project_type="kitchen"):
        """Step 1a: Create project"""
        print(f"\n📁 Step 1a: Creating project '{name}'")
        
        response = self.session.post(f"{self.base_url}/api/projects/", json={
            'name': name,
            'project_type': project_type
        })
        
        if response.status_code == 201:
            project = response.json()
            print(f"✅ Project created: {project['id']}")
            return project
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def upload_pdf(self, project_id, pdf_path):
        """Step 1b: Upload PDF"""
        print(f"\n📄 Step 1b: Uploading PDF from {pdf_path}")
        
        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            response = self.session.post(
                f"{self.base_url}/api/projects/{project_id}/upload_pdf/",
                files=files
            )
        
        if response.status_code == 202:
            data = response.json()
            print(f"✅ PDF uploaded: {data['filename']}")
            print(f"   Task ID: {data['task_id']}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def wait_for_pdf_processing(self, project_id, max_wait=120):
        """Wait for PDF conversion to complete"""
        print(f"\n⏳ Waiting for PDF processing...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/files/")
            
            if response.status_code == 200:
                data = response.json()
                status = data['pdf']['status']
                
                if status == 'completed':
                    print(f"✅ PDF processed: {data['pdf']['page_count']} pages")
                    return data
                elif status == 'failed':
                    print(f"❌ PDF processing failed")
                    return None
                else:
                    print(f"   Status: {status}...")
                    time.sleep(5)
            else:
                time.sleep(5)
        
        print(f"⏱️ Timeout")
        return None
    
    def extract_layout(self, project_id):
        """Step 2: Extract layout using Bedrock/OpenAI"""
        print(f"\n🔍 Step 2: Extracting layout with Bedrock (or OpenAI fallback)...")
        
        response = self.session.post(f"{self.base_url}/api/projects/{project_id}/extract_layout/")
        
        if response.status_code == 202:
            data = response.json()
            print(f"✅ Extraction queued: {data['pages_queued']} pages")
            print(f"   Task ID: {data['task_id']}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def wait_for_extraction(self, project_id, max_wait=180):
        """Wait for extraction to complete"""
        print(f"\n⏳ Waiting for extraction...")
        
        start_time = time.time()
        last_count = 0
        
        while time.time() - start_time < max_wait:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/extraction_results/")
            
            if response.status_code == 200:
                data = response.json()
                completed = sum(1 for e in data['extractions'] if e['status'] == 'completed')
                total = len(data['extractions'])
                total_items = sum(e['items_found'] for e in data['extractions'])
                
                if completed != last_count:
                    print(f"   Progress: {completed}/{total} pages extracted, {total_items} total items found")
                    last_count = completed
                
                if completed == total:
                    print(f"✅ Extraction completed!")
                    print(f"   📊 Breakdown:")
                    for extraction in data['extractions']:
                        print(f"      Page {extraction['page']}: {extraction['items_found']} items ({extraction['view_type']})")
                    return data
                
                time.sleep(10)
            elif response.status_code == 404:
                print(f"   Still processing...")
                time.sleep(10)
            else:
                print(f"   Checking... ({response.status_code})")
                time.sleep(10)
        
        print(f"⏱️ Timeout")
        return None
    
    def match_skus(self, project_id, tolerance=5.0):
        """Step 3: Match SKUs"""
        print(f"\n🔗 Step 3: Matching SKUs (tolerance: {tolerance}\")")
        
        response = self.session.post(
            f"{self.base_url}/api/projects/{project_id}/match_skus/",
            json={'dimension_tolerance': tolerance}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SKU matching completed: {data['total_matched']} matches")
            
            # Show all matches
            print(f"\n   📋 All SKU Matches:")
            for i, item in enumerate(data['matched_items'], 1):
                score_indicator = "🟢" if item['match_score'] >= 0.95 else "🟡" if item['match_score'] >= 0.8 else "🔴"
                print(f"      {i}. {item['label']} → {item['matched_sku']['code']} {score_indicator} (score: {item['match_score']:.2f})")
            
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def generate_pricing(self, project_id):
        """Step 4: Generate pricing"""
        print(f"\n💰 Step 4: Generating pricing...")
        
        response = self.session.post(f"{self.base_url}/api/projects/{project_id}/pricing/generate/")
        
        if response.status_code == 201:
            data = response.json()
            print(f"✅ Pricing generated:")
            print(f"   Items: {data['total_items']}")
            print(f"   Subtotal: ${data['subtotal']}")
            print(f"   Tax: ${data['tax']}")
            print(f"   Total: ${data['total']}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def generate_renders(self, project_id, style="modern"):
        """Step 5: Generate renders"""
        print(f"\n🎨 Step 5: Generating renders (style: {style})")
        
        response = self.session.post(
            f"{self.base_url}/api/projects/{project_id}/generate_renders/",
            json={'style': style}
        )
        
        if response.status_code == 202:
            data = response.json()
            print(f"✅ Rendering queued: {data['pages_queued']} pages")
            print(f"   Task ID: {data['task_id']}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def wait_for_renders(self, project_id, max_wait=600):
        """Wait for renders to complete"""
        print(f"\n⏳ Waiting for renders (this may take several minutes)...")
        
        start_time = time.time()
        last_completed = 0
        
        while time.time() - start_time < max_wait:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/renders/")
            
            if response.status_code == 200:
                data = response.json()
                completed = sum(1 for r in data['renders'] if r['status'] == 'completed')
                failed = sum(1 for r in data['renders'] if r['status'] == 'failed')
                total = len(data['renders'])
                
                if completed != last_completed:
                    print(f"   Progress: {completed}/{total} completed ({failed} failed)")
                    last_completed = completed
                
                if completed + failed == total:
                    if completed > 0:
                        print(f"✅ Rendering completed: {completed} successful, {failed} failed")
                        for render in data['renders']:
                            if render['status'] == 'completed':
                                print(f"   ✅ Page {render['page']}: {render['generation_time']:.1f}s")
                            elif render['status'] == 'failed':
                                print(f"   ❌ Page {render['page']}: {render.get('error', 'Unknown error')}")
                    return data
                
                time.sleep(15)
            elif response.status_code == 404:
                print(f"   Still processing...")
                time.sleep(15)
            else:
                time.sleep(15)
        
        print(f"⏱️ Timeout")
        return None
    
    def get_summary(self, project_id):
        """Get project summary"""
        print(f"\n📊 Getting project summary...")
        
        response = self.session.get(f"{self.base_url}/api/projects/{project_id}/summary/")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Project Summary:")
            print(f"   Name: {data['name']}")
            print(f"   Type: {data['project_type']}")
            print(f"   Completion: {data['completion_percentage']:.0f}%")
            print(f"   Stages completed: {', '.join(data['stages_completed'])}")
            
            if 'extraction' in data:
                print(f"\n   📄 Extraction:")
                print(f"      Pages: {data['extraction']['pages_extracted']}")
                print(f"      Items: {data['extraction']['total_items']}")
            
            if 'sku_matching' in data:
                print(f"\n   🔗 SKU Matching:")
                print(f"      Matches: {data['sku_matching']['total_matches']}")
                print(f"      Avg Score: {data['sku_matching']['average_score']:.2f}")
            
            if 'pricing' in data:
                print(f"\n   💰 Pricing:")
                print(f"      Total: ${data['pricing']['total']}")
                print(f"      Status: {data['pricing']['status']}")
            
            if 'rendering' in data:
                print(f"\n   🎨 Rendering:")
                print(f"      Completed: {data['rendering']['completed']}/{data['rendering']['total_renders']}")
                print(f"      Failed: {data['rendering']['failed']}")
            
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def run_complete_pipeline(self, pdf_path, project_name="Bedrock Test Kitchen", style="modern"):
        """
        Run complete pipeline end-to-end with Bedrock
        """
        print("\n" + "="*70)
        print("🚀 BEDROCK PIPELINE TEST - COMPLETE WORKFLOW")
        print("="*70)
        
        start_time = time.time()
        
        # Step 0: Auth
        if not self.register_and_login():
            return False
        
        # Step 1: Create project & upload PDF
        project = self.create_project(project_name, "kitchen")
        if not project:
            return False
        
        project_id = project['id']
        
        # Upload PDF
        upload = self.upload_pdf(project_id, pdf_path)
        if not upload:
            return False
        
        # Wait for PDF processing
        pdf_data = self.wait_for_pdf_processing(project_id)
        if not pdf_data:
            return False
        
        # Step 2: Extract layout (using Bedrock)
        extraction = self.extract_layout(project_id)
        if not extraction:
            return False
        
        # Wait for extraction
        extraction_data = self.wait_for_extraction(project_id)
        if not extraction_data:
            return False
        
        # Step 3: Match SKUs
        sku_matches = self.match_skus(project_id, tolerance=5.0)
        if not sku_matches:
            return False
        
        # Step 4: Generate pricing
        pricing = self.generate_pricing(project_id)
        if not pricing:
            print("⚠️ Pricing generation failed, but continuing...")
        
        # Step 5: Generate renders
        renders = self.generate_renders(project_id, style)
        if not renders:
            print("⚠️ Rendering failed, but continuing to summary...")
        else:
            # Wait for renders
            render_data = self.wait_for_renders(project_id)
        
        # Final summary
        summary = self.get_summary(project_id)
        
        elapsed = time.time() - start_time
        
        print("\n" + "="*70)
        print(f"✅ PIPELINE COMPLETED in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
        print("="*70)
        print(f"\n📍 Project ID: {project_id}")
        print(f"🌐 View at: {self.base_url}/admin/design_agent/project/{project_id}/")
        
        # Validation Report
        print("\n📋 VALIDATION REPORT:")
        print("-" * 70)
        
        if extraction_data:
            total_skus = sum(e['items_found'] for e in extraction_data['extractions'])
            print(f"✅ Extraction: {total_skus} SKUs detected from {len(extraction_data['extractions'])} pages")
        
        if sku_matches:
            exact_matches = sum(1 for m in sku_matches['matched_items'] if m['match_score'] >= 0.95)
            print(f"✅ SKU Matching: {sku_matches['total_matched']} matched ({exact_matches} exact matches)")
        
        if pricing:
            print(f"✅ Pricing: ${pricing['total']} total")
        
        print("-" * 70)
        
        return True


# Main execution
if __name__ == "__main__":
    import sys
    
    # Get PDF path
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "610_kitchen.pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ PDF file not found: {pdf_path}")
        print(f"Usage: python test_bedrock_pipeline.py <path_to_pdf>")
        sys.exit(1)
    
    # Run test
    tester = BedrockPipelineTester(base_url="http://localhost:8000")
    success = tester.run_complete_pipeline(
        pdf_path=pdf_path,
        project_name="Hillsborough Display Kitchen (Bedrock Test)",
        style="modern"
    )
    
    sys.exit(0 if success else 1)