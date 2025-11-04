import boto3
import json
from django.conf import settings

def get_bedrock_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=settings.AWS_DEFAULT_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

def call_bedrock(prompt):
    """Call Claude model hosted on AWS Bedrock"""
    client = get_bedrock_client()

    response = client.invoke_model(
        modelId=settings.BEDROCK_MODEL_ID,
        body=json.dumps({
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
            "max_tokens": 1024,
        })
    )

    result = json.loads(response['body'].read())
    return result["content"][0]["text"]
