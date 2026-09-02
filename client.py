import json

import boto3
from dotenv import load_dotenv

load_dotenv()

bedrock = boto3.client("bedrock-runtime", region_name="ap-southeast-1")


def perguntar(prompt: str) -> str:
    resp = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            }
        ),
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


if __name__ == "__main__":
    print(perguntar("Olá! Quem é você?"))
