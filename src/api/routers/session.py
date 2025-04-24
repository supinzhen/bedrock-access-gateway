from typing import Annotated
import logging
from fastapi import APIRouter, Depends, HTTPException, Path

import boto3
from botocore.config import Config

from api.auth import api_key_auth
#from api.models.bedrock import BedrockModel
from api.models.bedrock_agents import BedrockAgents
from api.schema import Models, Model, ErrorMessage
from api.setting import (DEBUG, AWS_REGION, DEFAULT_KB_MODEL, KB_PREFIX, AGENT_PREFIX)

from api.routers import model 

logger = logging.getLogger(__name__)
config = Config(connect_timeout=1, read_timeout=120, retries={"max_attempts": 1})


router = APIRouter(
    prefix="/clear_agent_memory",
    dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

bedrock_agent_runtime = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION,
    config=config,
)

router = APIRouter(
    prefix="/create_session",
    dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

@router.get("",)
async def get_create_session():    
    try:
        return model.chat_model.ini_create_session()
    except Exception as e:
        logger.error(f"Failed to create session : {str(e)}")
        raise HTTPException(status_code=500, detail="Error create session")    