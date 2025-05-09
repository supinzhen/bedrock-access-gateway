from typing import Annotated

from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
import logging
from api.auth import api_key_auth
#from api.models.bedrock import BedrockModel
from api.models.bedrock_agents import BedrockAgents
from api.schema import ChatRequest, ChatResponse, ChatStreamResponse
from api.setting import DEFAULT_MODEL

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    dependencies=[Depends(api_key_auth)],
    # responses={404: {"description": "Not found"}},
)


@router.post("/completions", response_model=ChatResponse | ChatStreamResponse, response_model_exclude_unset=True)
async def chat_completions(
        chat_request: Annotated[
            ChatRequest,
            Body(
                examples=[
                    {
                        "user": "SessionID",
                        "model": "anthropic.claude-3-sonnet-20240229-v1:0",
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": "Hello!"},
                        ],
                    }
                ],
            ),
        ]
):
    # this method gets called by front-end
    
    if chat_request.model.lower().startswith("gpt-"):
        chat_request.model = DEFAULT_MODEL

    # Exception will be raised if model not supported.
    model = BedrockAgents()
    # model.validate(chat_request)
    if chat_request.stream:
        response = StreamingResponse(content=model.chat_stream(chat_request), media_type="text/event-stream")
        return response
     
    return model.chat(chat_request)