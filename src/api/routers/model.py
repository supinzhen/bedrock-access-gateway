from typing import Annotated
import logging
from fastapi import APIRouter, Depends, HTTPException, Path

from api.auth import api_key_auth
#from api.models.bedrock import BedrockModel
from api.models.bedrock_agents import BedrockAgents
from api.schema import Models, Model
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/models",
    dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)

#chat_model = BedrockModel()
chat_model = BedrockAgents()

async def validate_model_id(model_id: str):
    logger.info(f"validate_model_id: {model_id}")
    if model_id not in chat_model.list_models():
        raise HTTPException(status_code=500, detail="Unsupported Model Id")


@router.get("", response_model=Models)
async def list_models():
    try:
        
        model_list = [
            Model(id=model_id) for model_id in chat_model.list_models()
        ]
        return Models(data=model_list)
    except Exception as e:
        logger.error(f"Failed to list models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error listing models")
    # model_list = [
    #     Model(id=model_id) for model_id in chat_model.list_models()
    # ]
    # return Models(data=model_list)


@router.get(
    "/{model_id}",
    response_model=Model,
)
async def get_model(
        model_id: Annotated[
            str,
            Path(description="Model ID", example="anthropic.claude-3-sonnet-20240229-v1:0"),
        ]
):
    logger.info(f"get_model: {model_id}")
    await validate_model_id(model_id)
    return Model(id=model_id)