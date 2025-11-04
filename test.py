"""
Complete Pipeline Test Script
Run this to test your entire workflow from PDF to final output
"""

import requests
import time
import json
from pathlib import Path


class PipelineTester:
    """Test complete design agent pipeline"""
    
    def __init__(self, base_url="http://localhost:8000", api_key=None):
        self.base_url = base_url
        self.token = api_key
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({'Authorization': f'Token {self.token}'})
    
    def register_and_login(self, username, password, email):
        """Step 0: Authentication"""
        print("\n🔐 Step 0: Authentication")
        
        # Register
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
            # Try login if registration fails
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
    
    def wait_for_pdf_processing(self, project_id, max_wait=60):
        """Wait for PDF to finish processing"""
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
                print(f"❌ Failed to check status: {response.text}")
                return None
        
        print(f"⏱️ Timeout waiting for PDF processing")
        return None
    
    def extract_layout(self, project_id):
        """Step 2: Extract layout"""
        print(f"\n🔍 Step 2: Extracting layout...")
        
        response = self.session.post(f"{self.base_url}/api/projects/{project_id}/extract_layout/")
        
        if response.status_code == 202:
            data = response.json()
            print(f"✅ Extraction queued: {data['pages_queued']} pages")
            print(f"   Task ID: {data['task_id']}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def wait_for_extraction(self, project_id, max_wait=120):
        """Wait for extraction to complete"""
        print(f"\n⏳ Waiting for extraction...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/extraction_results/")
            
            if response.status_code == 200:
                data = response.json()
                completed = sum(1 for e in data['extractions'] if e['status'] == 'completed')
                total = len(data['extractions'])
                
                print(f"   Progress: {completed}/{total} pages extracted")
                
                if completed == total:
                    print(f"✅ Extraction completed: {sum(e['items_found'] for e in data['extractions'])} total items")
                    return data
                
                time.sleep(10)
            elif response.status_code == 404:
                print(f"   Still processing...")
                time.sleep(10)
            else:
                print(f"❌ Failed: {response.text}")
                return None
        
        print(f"⏱️ Timeout waiting for extraction")
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
            
            # Show sample matches
            for item in data['matched_items'][:3]:
                print(f"   {item['label']} → {item['matched_sku']['code']} (score: {item['match_score']:.2f})")
            
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
    
    def wait_for_renders(self, project_id, max_wait=300):
        """Wait for renders to complete"""
        print(f"\n⏳ Waiting for renders (this may take a while)...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = self.session.get(f"{self.base_url}/api/projects/{project_id}/renders/")
            
            if response.status_code == 200:
                data = response.json()
                completed = sum(1 for r in data['renders'] if r['status'] == 'completed')
                failed = sum(1 for r in data['renders'] if r['status'] == 'failed')
                total = len(data['renders'])
                
                print(f"   Progress: {completed}/{total} renders completed ({failed} failed)")
                
                if completed + failed == total:
                    print(f"✅ Rendering completed: {completed} successful, {failed} failed")
                    return data
                
                time.sleep(15)
            elif response.status_code == 404:
                print(f"   Still processing...")
                time.sleep(15)
            else:
                print(f"❌ Failed: {response.text}")
                return None
        
        print(f"⏱️ Timeout waiting for renders")
        return None
    
    def get_project_summary(self, project_id):
        """Get complete project summary"""
        print(f"\n📊 Getting project summary...")
        
        response = self.session.get(f"{self.base_url}/api/projects/{project_id}/summary/")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Project Summary:")
            print(f"   Name: {data['name']}")
            print(f"   Type: {data['project_type']}")
            print(f"   Completion: {data['completion_percentage']:.0f}%")
            print(f"   Stages completed: {', '.join(data['stages_completed'])}")
            return data
        else:
            print(f"❌ Failed: {response.text}")
            return None
    
    def run_complete_pipeline(self, pdf_path, project_name="Test Kitchen", style="modern"):
        """
        Run complete pipeline end-to-end
        
        Args:
            pdf_path: Path to PDF file
            project_name: Name for the project
            style: Rendering style
        """
        print("\n" + "="*60)
        print("🚀 STARTING COMPLETE PIPELINE TEST")
        print("="*60)
        
        start_time = time.time()
        
        # Step 0: Auth
        auth = self.register_and_login(
            username="test_user",
            password="test_password_123",
            email="test@example.com"
        )
        if not auth:
            return False
        
        # Step 1: Create project and upload PDF
        project = self.create_project(project_name, "kitchen")
        if not project:
            return False
        
        project_id = project['id']
        
        # Step 1b: Upload PDF
        upload = self.upload_pdf(project_id, pdf_path)
        if not upload:
            return False
        
        # Wait for PDF processing
        pdf_data = self.wait_for_pdf_processing(project_id)
        if not pdf_data:
            return False
        
        # Step 2: Extract layout
        extraction = self.extract_layout(project_id)
        if not extraction:
            return False
        
        # Wait for extraction
        extraction_data = self.wait_for_extraction(project_id)
        if not extraction_data:
            return False
        
        # Step 3: Match SKUs
        sku_matches = self.match_skus(project_id)
        if not sku_matches:
            return False
        
        # Step 4: Generate pricing
        pricing = self.generate_pricing(project_id)
        if not pricing:
            print("⚠️ Pricing generation failed, but continuing...")
        
        # Step 5: Generate renders
        renders = self.generate_renders(project_id, style)
        if not renders:
            return False
        
        # Wait for renders
        render_data = self.wait_for_renders(project_id)
        if not render_data:
            return False
        
        # Final summary
        summary = self.get_project_summary(project_id)
        
        elapsed = time.time() - start_time
        
        print("\n" + "="*60)
        print(f"✅ PIPELINE COMPLETED SUCCESSFULLY in {elapsed:.0f} seconds!")
        print("="*60)
        print(f"\n📍 Project ID: {project_id}")
        print(f"📄 View in browser: {self.base_url}/admin (or your frontend URL)")
        
        return True


# Usage example
if __name__ == "__main__":
    import sys
    
    # Get PDF path from command line or use default
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "test_kitchen.pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ PDF file not found: {pdf_path}")
        print(f"Usage: python pipeline_test.py <path_to_pdf>")
        sys.exit(1)
    
    # Run pipeline test
    tester = PipelineTester(base_url="http://localhost:8000")
    success = tester.run_complete_pipeline(
        pdf_path=pdf_path,
        project_name="Hillsborough Display Kitchen",
        style="modern"
    )
    
    sys.exit(0 if success else 1)