import os

DEFAULT_API_KEYS = "bedrock"

API_ROUTE_PREFIX = "/api/v1"

TITLE = "Amazon Bedrock Proxy APIs"
SUMMARY = "OpenAI-Compatible RESTful APIs for Amazon Bedrock"
VERSION = "0.1.0"
DESCRIPTION = """
Use OpenAI-Compatible RESTful APIs for Amazon Bedrock models.
"""

DEBUG = os.environ.get("DEBUG", "false").lower() != "true"
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
DEFAULT_MODEL = os.environ.get(
    "DEFAULT_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0"
)
DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "DEFAULT_EMBEDDING_MODEL", "cohere.embed-multilingual-v3"
)
ENABLE_CROSS_REGION_INFERENCE = os.environ.get("ENABLE_CROSS_REGION_INFERENCE", "true").lower() != "false"

KB_PREFIX = 'kb-'
AGENT_PREFIX = 'ag-'

DEFAULT_KB_MODEL = os.environ.get(
    "DEFAULT_KB_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)


DEFAULT_KB_MODEL_ARN = f'arn:aws:bedrock:{AWS_REGION}::foundation-model/{DEFAULT_KB_MODEL}'