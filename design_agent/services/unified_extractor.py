import os
import base64
import logging
import json
from typing import Dict
from django.conf import settings
import boto3
import openai

logger = logging.getLogger('design_agent')


class UnifiedExtractor:
    """
    Extracts SKU codes and dimensions from CAD drawings
    Uses Bedrock Claude 3.7 Sonnet (primary) with OpenAI GPT-4o fallback
    """

    def __init__(self):
        # Initialize Bedrock
        self.bedrock_available = False
        try:
            # Get AWS credentials
            aws_region = getattr(settings, 'AWS_DEFAULT_REGION', 'eu-north-1')
            aws_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
            aws_secret = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
            
            if not aws_key or not aws_secret:
                raise ValueError("AWS credentials not found in settings")
            
            self.bedrock_client = boto3.client(
                service_name='bedrock-runtime',
                region_name=aws_region,
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret
            )
            
            # CRITICAL: Use ARN, not MODEL_ID for Claude 3.7
            # ARN is required for inference profiles
            model_arn = getattr(settings, "BEDROCK_MODEL_ARN", None)
            model_id = getattr(settings, "BEDROCK_MODEL_ID", None)
            
            # Prefer ARN over MODEL_ID
            if model_arn:
                self.bedrock_model = model_arn
                logger.info(f"✅ Using Bedrock MODEL ARN: {model_arn}")
            elif model_id:
                # Construct ARN from MODEL_ID if ARN not provided
                # Format: arn:aws:bedrock:region:account:inference-profile/model-id
                logger.warning("⚠️ MODEL_ARN not found, using MODEL_ID (may fail)")
                self.bedrock_model = model_id
            else:
                raise ValueError("Neither BEDROCK_MODEL_ARN nor BEDROCK_MODEL_ID found in settings")
            
            # Test connection with STS
            sts = boto3.client(
                'sts',
                region_name=aws_region,
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret
            )
            identity = sts.get_caller_identity()
            
            self.bedrock_available = True
            logger.info(f"✅ Bedrock client initialized successfully")
            logger.info(f"   Model: {self.bedrock_model}")
            logger.info(f"   Region: {aws_region}")
            logger.info(f"   Account: {identity['Account']}")
            
        except Exception as e:
            logger.error(f"❌ Bedrock initialization failed: {e}")
            logger.warning("   Will use OpenAI fallback for all requests")

        # Initialize OpenAI fallback
        try:
            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("✅ OpenAI client initialized as fallback")
        except Exception as e:
            logger.error(f"❌ OpenAI initialization failed: {e}")

    def extract_from_image(self, image_path: str) -> Dict:
        """Extracts data from image via Claude 3.7 Sonnet → fallback to GPT-4o"""
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Try Bedrock Claude 3.7 first (if available)
        if self.bedrock_available:
            try:
                logger.info("🔷 Attempting extraction with Claude 3.7 Sonnet (Bedrock)...")
                logger.info(f"   Using model: {self.bedrock_model}")
                result = self._extract_with_bedrock(image_data)
                logger.info("✅ Claude 3.7 extraction successful")
                return result
            except Exception as e:
                logger.error(f"❌ Claude 3.7 extraction failed: {e}")
                logger.info("🔄 Falling back to OpenAI GPT-4o...")

        # Fallback to OpenAI GPT-4o
        logger.info("🟢 Using OpenAI GPT-4o fallback...")
        result = self._extract_with_openai(image_data)
        logger.info("✅ OpenAI extraction successful")
        return result

    def _extract_with_bedrock(self, image_data: bytes) -> Dict:
        """Extract using AWS Bedrock Claude 3.7 Sonnet (Vision + Text)"""

        image_base64 = base64.b64encode(image_data).decode('utf-8')
        prompt = self._build_extraction_prompt()

        # Claude 3.7 API request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "temperature": 0,
            "top_k": 250,
            "top_p": 0.999,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        logger.info(f"📤 Invoking Bedrock model: {self.bedrock_model}")
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.bedrock_model,  # This MUST be ARN for Claude 3.7
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )

            response_body = json.loads(response['body'].read())
            raw_text = response_body["content"][0]["text"]

            structured_data = self._parse_json_response(raw_text)

            return {
                "structured_data": structured_data,
                "raw_response": raw_text,
                "service": "bedrock_claude_3_7_sonnet_v1"
            }
        except Exception as e:
            logger.error(f"❌ Bedrock API error: {str(e)}")
            raise

    def _extract_with_openai(self, image_data: bytes) -> Dict:
        """Extract using OpenAI GPT-4o (fallback)"""

        image_base64 = base64.b64encode(image_data).decode('utf-8')
        prompt = self._build_extraction_prompt()

        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CAD drawing analyst. Extract SKU codes and dimensions with perfect accuracy. Return ONLY valid JSON."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4000,
            temperature=0,
            response_format={"type": "json_object"}
        )

        raw_text = response.choices[0].message.content
        structured_data = json.loads(raw_text)

        return {
            "structured_data": structured_data,
            "raw_response": raw_text,
            "service": "openai_gpt4o"
        }

    def _build_extraction_prompt(self) -> str:
        """Prompt optimized for SKU and dimension extraction"""
        return """You are analyzing a CAD kitchen or bathroom layout drawing. 
Extract EVERY visible SKU code with extreme thoroughness.

**CRITICAL INSTRUCTIONS:**

1. **SKU CODES** - EXTRACT ALL:
   - Scan the ENTIRE drawing systematically (left to right, top to bottom)
   - Include ALL characters EXACTLY as written: BC242484-1TDL, W2130-15L, SB42FH, FLAT PNL 3/4, etc.
   - Look in ALL locations: inside cabinets, above items, below items, in corners
   - Extract codes with dashes (-), slashes (/), spaces - keep them EXACT
   - Common patterns: BC/SB/DB/B (base), W/WP (wall), OV (oven), DISH/BI/CKT (appliance), FLAT PNL/USF/FL (panels/fillers)
   - Extract EVERY code, even duplicates (count them separately)
   - Typical elevation has 15-30 codes - scan until you find them all

2. **DIMENSIONS** - Read carefully:
   - Find dimension lines (arrows/ticks with numbers)
   - Extract EXACT values: 24", 42 3/8", 67 1/2"
   - Convert fractions to decimals: 3/8"=0.375, 1/2"=0.5, 1/4"=0.25, 3/16"=0.1875, 9/16"=0.5625
   - Width = horizontal measurements
   - Height = vertical measurements  
   - Depth = usually noted separately (common: 15", 24")
   - If dimension is unclear or not visible, use null

3. **POSITION** - Estimate X,Y:
   - X: horizontal distance from left edge (inches)
   - Y: vertical distance from top edge (inches)
   - Use dimension lines to calculate positions
   - Base cabinets typically Y > 30", wall cabinets Y < 30"

4. **CATEGORY** - Classify from code:
   - BC/SB/DB/B/BTB → "base_cabinet"
   - W/WP → "wall_cabinet"  
   - OV/VP → "oven_cabinet"
   - BI/DISH/CKT/SFU/CPRU/MW/REF → "appliance"
   - FLAT PNL/PNL → "panel"
   - USF/FL/FSEP → "filler"
   - DOOR → "door"
   - HIN → "hardware"

**OUTPUT FORMAT (STRICT JSON):**

{
  "view_type": "elevation",
  "total_skus": 22,
  "items": [
    {
      "label": "BC242484-1TDL",
      "category": "base_cabinet",
      "dimensions": {"width": 24.0, "height": 84.0, "depth": 24.0},
      "position": {"x": 0, "y": 120},
      "notes": "Tall deep base corner cabinet left"
    },
    {
      "label": "W2130-15L",
      "category": "wall_cabinet",
      "dimensions": {"width": 21.0, "height": 30.0, "depth": 15.0},
      "position": {"x": 24, "y": 0},
      "notes": "Wall cabinet 15 inch deep left"
    },
    {
      "label": "FLAT PNL 3/4",
      "category": "panel",
      "dimensions": {"width": null, "height": null, "depth": 0.75},
      "position": {"x": 100, "y": 50},
      "notes": "Decorative panel"
    }
  ]
}

**VALIDATION CHECKLIST:**
✓ Scanned entire drawing left-to-right, top-to-bottom
✓ Found ALL cabinet codes (BC/SB/DB/W/WP/OV)
✓ Found ALL appliance codes (DISH/BI/CKT)
✓ Found ALL panel/filler codes (FLAT PNL/USF/FL/FSEP)
✓ Found ALL hardware codes (DOOR/HIN)
✓ Total count matches visual inspection (typical: 15-30 per elevation)
✓ Every code extracted EXACTLY as shown (preserve dashes, slashes, spaces)

Extract EVERY visible code. Be exhaustive and meticulous."""

    def _parse_json_response(self, raw_text: str) -> Dict:
        """Safely extract JSON even if wrapped in Markdown"""
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in raw_text or "```" in raw_text:
                start = raw_text.find("{")
                end = raw_text.rfind("}") + 1
                if start != -1 and end != 0:
                    return json.loads(raw_text[start:end])
            raise ValueError("Could not extract JSON from response")

    def validate_extraction(self, data: Dict) -> bool:
        """Validate extraction structure"""
        if not isinstance(data, dict):
            return False
        required_fields = ["view_type", "items"]
        if not all(field in data for field in required_fields):
            return False
        if not isinstance(data["items"], list):
            return False
        for item in data["items"]:
            if "label" not in item or "category" not in item:
                return False
        return True