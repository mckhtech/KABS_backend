# KABS Backend (Design Agent API)

The KABS Backend is a sophisticated Django-based application serving as a Design Agent API. It allows users to upload architectural or interior design PDFs, extract layouts, identify and match products (SKUs), estimate pricing, and generate 2D/3D renders using AI. 

## Tech Stack
* **Framework**: Django & Django REST Framework (DRF)
* **Database**: PostgreSQL (via `psycopg2`) & ChromaDB (for vector/semantic SKU search)
* **Task Queue**: Celery with Redis broker
* **AI & Machine Learning**: 
  * Google Generative AI / Cloud AI Platform
  * OpenAI
* **Cloud & Storage**: AWS (boto3)
* **PDF Processing**: `pdf2image`, ReportLab for final PDF generation
* **Authentication**: JWT authentication (`djangorestframework-simplejwt`)

## Workflow Overview
1. **Authentication**: Users sign up and obtain a JWT token.
2. **Project Creation**: A design project is created.
3. **Upload & Extraction**: User uploads a design PDF. The AI extracts layout information and objects from the PDF pages.
4. **SKU Matching & Validation**: The extracted layout items are matched to known SKUs in the ChromaDB database. The user validates the matches or replaces them.
5. **Rendering & 3D Previews**: The system generates realistic renders (2D and 3D) based on the matched SKUs and layout.
6. **Pricing Estimation**: A cost estimate is generated based on the identified items. Users can adjust, add custom items, or lock the pricing.
7. **Annotations & Approval**: Users can annotate the renders, and ultimately approve the project.
8. **Report Generation**: A customized PDF report with the renders, pricing, and project summary is generated for download.

## API Documentation

The API follows RESTful principles and is mounted at `/api/`. All endpoints requiring user identification expect a valid JWT Bearer Token.

### 1. Authentication
* `POST /api/auth/register/` - Register a new user.
* `POST /api/auth/login/` - Authenticate and receive `access` and `refresh` tokens.
* `POST /api/auth/logout/` - Invalidate current session tokens.
* `GET /api/auth/profile/` - Get authenticated user profile details.

### 2. Project Management
* `GET /api/projects/` - List all projects for the user.
* `POST /api/projects/` - Create a new project.
* `GET /api/projects/{id}/` - Retrieve project details.
* `PUT/PATCH /api/projects/{id}/` - Update a project name/description.
* `DELETE /api/projects/{id}/` - Delete a project.
* `POST /api/projects/{id}/duplicate/` - Duplicate an existing project.
* `GET /api/projects/{id}/edit/` - Load the project into the editing interface.
* `PUT/PATCH /api/projects/{id}/metadata/` - Update abstract project metadata.

### 3. Core Processing Flow
* `GET /api/projects/{id}/status/` - Check the background processing status.
* `GET /api/projects/{id}/summary/` - Retrieve a full project summary including items and base pricing.
* `POST /api/projects/{id}/upload_pdf/` - Upload the initial design PDF.
* `GET /api/projects/{id}/files/` - List assigned files.
* `POST /api/projects/{id}/extract_layout/` - Trigger AI to analyze the PDF and extract items.
* `GET /api/projects/{id}/extraction_results/` - Check layout extraction output.
* `POST /api/projects/{id}/match_skus/` - Match extracted items computationally to the internal SKU vector database.
* `GET /api/projects/{id}/validate_skus/` - Fetch images of matching SKUs for validation.
* `POST /api/projects/{id}/skus/replace/` - Manually replace a matched SKU with an alternative.

### 4. Rendering
* `POST /api/projects/{id}/generate_renders/` - Trigger 2D render generation.
* `GET /api/projects/{id}/renders/` - Fetch all completed renders.
* `POST /api/projects/{id}/renders/{render_id}/regenerate/` - Regenerate a specific render if not satisfied.
* `GET /api/projects/{id}/renders/history/` - View the version history of renders.
* `POST /api/projects/{id}/pages/{page_number}/generate_3d_preview/` - Generate a 3D preview for a page.
* `POST /api/projects/{id}/generate_all_3d_previews/` - Batch 3D preview generation.
* `GET /api/projects/{id}/pages/{page_number}/3d_preview/` - Fetch a generated 3D preview.

### 5. Pricing
* `POST /api/projects/{id}/pricing/generate/` - Auto-generate pricing details.
* `GET /api/projects/{id}/pricing/` - Fetch existing pricing breakdown.
* `POST /api/projects/{id}/pricing/items/` - Add custom/manual pricing items (e.g., labor).
* `PUT/PATCH /api/projects/{id}/pricing/items/{item_id}/` - Update the cost/quantity of a pricing item.
* `DELETE /api/projects/{id}/pricing/items/{item_id}/delete/` - Remove a pricing item.
* `POST /api/projects/{id}/pricing/update/` - Refresh overall project pricing totals.
* `POST /api/projects/{id}/pricing/lock/` - Lock the pricing estimate (disallow updates).
* `POST /api/projects/{id}/pricing/unlock/` - Unlock the pricing estimate.

### 6. Annotations & Review
* `GET /api/projects/{id}/annotations/` - Fetch all user annotations for a render.
* `POST /api/projects/{id}/annotations/create/` - Create a new mark/annotation.
* `PUT/PATCH /api/projects/{id}/annotations/{annotation_id}/` - Edit annotation.
* `DELETE /api/projects/{id}/annotations/{annotation_id}/delete/` - Delete annotation.

### 7. Approval & Reporting
* `POST /api/projects/{id}/approve/` - Approve the finalized project design and pricing.
* `POST /api/projects/{id}/unapprove/` - Unapprove.
* `GET /api/projects/{id}/approval/` - Check the project's approval status.
* `GET /api/projects/{id}/download_report/` - Generate and download the final comprehensive PDF containing layout, renders, and pricing breakdown.

## Installation & Setup

1. **Clone the repository.**
2. **Setup Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Variables**: Setup a `.env` file in the root containing your database details, AWS keys, OpenAI API key, and Google Cloud credentials.
5. **Database Setup**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```
6. **Start Redis**: Ensure Redis is running locally or provide a valid Redis URL for Celery.
7. **Start Celery Worker**:
   ```bash
   celery -A ai_design_agent worker -l info
   ```
8. **Run the Application**:
   ```bash
   python manage.py runserver
   ```
