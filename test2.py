import boto3
import json
import os
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv  # 👈 Add this

# ✅ Load .env file before anything else
load_dotenv()

def test_bedrock_credentials():
    print("🔍 Checking AWS credentials and Bedrock access...\n")

    try:
        # 1️⃣ Print loaded keys (optional sanity check)
        print("AWS_ACCESS_KEY_ID:", os.getenv("AWS_ACCESS_KEY_ID"))
        print("AWS_SECRET_ACCESS_KEY:", os.getenv("AWS_SECRET_ACCESS_KEY")[:6] + "..." if os.getenv("AWS_SECRET_ACCESS_KEY") else "None")
        print()

        # 2️⃣ Check if boto3 can find credentials
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print("✅ AWS credentials found!")
        print(f"👤 Account ID: {identity['Account']}")
        print(f"🧩 ARN: {identity['Arn']}\n")

        # 3️⃣ Test Bedrock connection
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 20,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Hello!"}]}
            ]
        }

        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-7-sonnet-20250219-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )

        result = json.loads(response["body"].read())
        print("✅ Bedrock model invoked successfully!")
        print("💬 Response:", result["content"][0]["text"])

    except NoCredentialsError:
        print("❌ No AWS credentials found.")
        print("💡 Fix: check that your .env file is in the same directory and `python-dotenv` is installed.")
    except ClientError as e:
        print("❌ AWS ClientError:", e)
    except Exception as e:
        print("❌ Unexpected error:", e)

if __name__ == "__main__":
    test_bedrock_credentials()
