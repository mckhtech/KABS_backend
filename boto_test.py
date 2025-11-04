import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import NoCredentialsError, ClientError
import json

def test_bedrock_credentials():
    print("📂 Current working directory:", os.getcwd())

    # Explicitly load .env from current dir
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
    print("🧾 Loading .env from:", os.path.join(os.getcwd(), ".env"))

    # Fetch credentials and model info
    aws_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    model_id = os.getenv("BEDROCK_MODEL_ID")
    model_arn = os.getenv("BEDROCK_MODEL_ARN")

    print("AWS_ACCESS_KEY_ID:", aws_key)
    print("AWS_DEFAULT_REGION:", aws_region)
    print("MODEL_ID:", model_id)
    print("MODEL_ARN:", model_arn)

    if not all([aws_key, aws_secret]):
        print("❌ No AWS credentials found.")
        return

    try:
        # Verify credentials
        sts = boto3.client("sts", region_name=aws_region)
        identity = sts.get_caller_identity()
        print("✅ AWS credentials valid!")
        print("👤 Account ID:", identity["Account"])
        print("🧩 ARN:", identity["Arn"])

        # Initialize Bedrock Runtime
        bedrock = boto3.client("bedrock-runtime", region_name=aws_region)

        print("\n🔍 Testing Bedrock model invocation...")
        try:
            # Construct proper payload for Claude 3
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "top_k": 250,
                "stop_sequences": [],
                "temperature": 1,
                "top_p": 0.999,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Hello from Django test!"}
                        ]
                    }
                ]
            }

            response = bedrock.invoke_model(
                modelId=model_arn or model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )

            print("✅ Model invocation success!")
            print("💬 Response:", response["body"].read().decode("utf-8"))

        except ClientError as e:
            print("❌ AWS ClientError:", e)
        except Exception as e:
            print("❌ Other error:", e)

    except NoCredentialsError:
        print("❌ AWS credentials not found or invalid.")
    except Exception as e:
        print("❌ Unexpected error:", e)


if __name__ == "__main__":
    test_bedrock_credentials()
