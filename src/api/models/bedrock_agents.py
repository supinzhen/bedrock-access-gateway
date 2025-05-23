import base64
import json
import logging
import re
import time
from abc import ABC
from typing import AsyncIterable
import uuid

import boto3
from botocore.config import Config
import numpy as np
import requests
import tiktoken
from fastapi import HTTPException
from api.models.model_manager import ModelManager

from api.models.bedrock import (
    BedrockModel, 
    bedrock_client, 
    bedrock_runtime)

from api.schema import (
    ChatResponse,
    ChatRequest,
    ChatResponseMessage,
    ChatStreamResponse,
    ChoiceDelta,
    Sesssion,
    ClearMemoryRequest
)
                                
from api.setting import (DEBUG, AWS_REGION, DEFAULT_KB_MODEL, KB_PREFIX, AGENT_PREFIX)

logger = logging.getLogger(__name__)
config = Config(connect_timeout=1, read_timeout=120, retries={"max_attempts": 1})

bedrock_agent = boto3.client(
            service_name="bedrock-agent",
            region_name=AWS_REGION,
            config=config,
        )

bedrock_agent_runtime = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION,
    config=config,
)


class BedrockAgents(BedrockModel):

    #bedrock_model_list = None
    def __init__(self):
        super().__init__()
        model_manager = ModelManager()
        # self.list_models()


    def list_models(self) -> list[str]:
        """Always refresh the latest model list"""
        self.model_manager.clear_models()
        super().list_models()
        self.get_kbs()
        self.get_agents()
        return list(self.model_manager.get_all_models().keys())
    
    # get list of active knowledge bases
    def get_kbs(self):

        # List knowledge bases
        response = bedrock_agent.list_knowledge_bases(maxResults=100)

        # Print knowledge base information
        for kb in response['knowledgeBaseSummaries']:
            name = f"{KB_PREFIX}{kb['knowledgeBaseId']}-{kb['name']}"
            val = {
                "system": True,      # Supports system prompts for context setting
                "multimodal": True,  # Capable of processing both text and images
                "tool_call": True,
                "stream_tool_call": True,
                "kb_id": kb['knowledgeBaseId'],
                "model_id": DEFAULT_KB_MODEL
            }
            #self.model_manager.get_all_models()[name] = val
            model = {}
            model[name]=val
            self.model_manager.add_model(model)
    
    def get_latest_agent_alias(self, client, agent_id):

        # List all aliases for the agent
        response = client.list_agent_aliases(
            agentId=agent_id,
            maxResults=100  # Adjust based on your needs
        )
        
        if not response.get('agentAliasSummaries'):
            return None
            
        # Sort aliases by creation time to get the latest one
        aliases = response['agentAliasSummaries']
        latest_alias = None
        latest_creation_time = None
        
        for alias in aliases:
            # Only consider aliases that are in PREPARED state
            if alias['agentAliasStatus'] == 'PREPARED':
                creation_time = alias.get('creationDateTime')
                if latest_creation_time is None or creation_time > latest_creation_time:
                    latest_creation_time = creation_time
                    latest_alias = alias
        
        if latest_alias:
            return latest_alias['agentAliasId']
            
        return None

    def get_agents(self):
        bedrock_ag = boto3.client(
            service_name="bedrock-agent",
            region_name=AWS_REGION,
            config=config,
        )
        # List Agents
        response = bedrock_agent.list_agents(maxResults=100)

        # Prepare agent for display
        for agent in response['agentSummaries']:
           
            if (agent['agentStatus'] != 'PREPARED'):
                continue
            
            agentId = agent['agentId']

            name = f"{AGENT_PREFIX}{agentId}-{agent['agentName']}"

            aliasId = self.get_latest_agent_alias(bedrock_ag, agentId)
            if (aliasId is None):
                continue
            
            response = bedrock_agent.get_agent(agentId=agentId)
                
            foundation_model = response['agent']["foundationModel"]

            val = {
                "system": False,      # Supports system prompts for context setting. These are already set in Bedrock Agent configuration
                "multimodal": True,  # Capable of processing both text and images
                "tool_call": False,  # Tool Use not required for Agents
                "stream_tool_call": False,
                "agent_id": agentId,
                "alias_id": aliasId,
                "foundation_model" : foundation_model,
            }
            #self.model_manager.get_all_models()[name] = val
            model = {}
            model[name]=val
            self.model_manager.add_model(model)
    

    def _invoke_bedrock(self, chat_request: ChatRequest, stream=False):
        """Common logic for invoke bedrock models"""

        # convert OpenAI chat request to Bedrock SDK request
        args = self._parse_request(chat_request)
        if DEBUG:
            logger.info("Bedrock request: " + json.dumps(str(args)))

        try:
            if stream:
                response = bedrock_runtime.converse_stream(**args)
            else:
                response = bedrock_runtime.converse(**args)


        except bedrock_client.exceptions.ValidationException as e:
            logger.error("Validation Error: " + str(e))
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=str(e))
        return response
    
    def chat(self, chat_request: ChatRequest) -> ChatResponse:
        """Default implementation for Chat API."""
        message_id = self.generate_message_id()
        
        bedrock_agent = boto3.client(
            service_name="bedrock-agent",
            region_name=AWS_REGION,
            config=config,
        )

        bedrock_agent_runtime = boto3.client(
            service_name="bedrock-agent-runtime",
            region_name=AWS_REGION,
            config=config,
        )
        
        if chat_request.model.startswith(KB_PREFIX):
            response = self._invoke_kb(chat_request, stream=False)
        elif chat_request.model.startswith(AGENT_PREFIX):
            try:
                
                args = self._parse_request(chat_request)
                
                # model = self.model_manager.get_all_models()[chat_request.model]
                
                query = args['messages'][0]['content'][0]['text']
                messages = args['messages']
                query = messages[len(messages)-1]['content'][0]['text']
                

                
                agentId =  chat_request.model.split('-')[1]
                agent_response = bedrock_agent.get_agent(agentId=agentId)
                alias_id = 'TSTALIASID'
                
                foundationModel = agent_response['agent']['foundationModel']
                
                logger.info("agentId: " + str(agentId))
                logger.info("alias_id: " + str(alias_id))
                logger.info("invocationId: " + str(foundationModel))
                    
                # 呼叫 Agent
                response = bedrock_agent_runtime.invoke_agent(
                    agentId= agentId,
                    agentAliasId= alias_id,
                    sessionId=chat_request.user,
                    inputText=query,
                    sessionState={'invocationId': str(foundationModel)}
                )

                
                # 處理流式回應 (非流式請用 converse API)
                completion = ""
                for event in response["completion"]:
                    chunk = event["chunk"]
                    completion += chunk["bytes"].decode("utf-8")
                    
                # response_agent = bedrock_agent.get_agent(agentId=model['agent_id'])
                    
                # foundation_model = response_agent['agent']["foundationModel"]
                
                agent_info = str(chat_request.model) + "/" + str(agentId) + "/" + str(alias_id) + "/" + str(foundationModel)
                
                return ChatResponse(id=message_id,  # 生成唯一ID
                                    model=agent_info,
                                    choices=[{
                                        "index": 0,
                                        "message": {"role": "assistant", "content": completion},
                                        "finish_reason": "stop",
                                    }],
                                    usage={
                                        "prompt_tokens": 12,
                                        "completion_tokens": 38,
                                        "total_tokens": 50
                                    }
                                )
            except Exception as e:
                logger.error(f"Failed to Invoke Agent: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to Invoke Agent: {str(e)}")
                
        else:
            response = self._invoke_bedrock(chat_request, stream=False)
            # Standard Bedrock response processing
            # content = response["output"]["message"]["content"]
            # finish_reason = response["stopReason"]
            # usage = response["usage"]

        output_message = response["output"]["message"]
        input_tokens = response["usage"]["inputTokens"]
        output_tokens = response["usage"]["outputTokens"]
        finish_reason = response["stopReason"]

        chat_response = self._create_response(
            model=chat_request.model,
            message_id=message_id,
            content=output_message["content"],
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        if DEBUG:
            logger.info("Proxy response :" + chat_response.model_dump_json())
        return chat_response

    # def chat(self, chat_request: ChatRequest) -> ChatResponse:
    #     """Default implementation for Chat API."""

    #     message_id = self.generate_message_id()
    #     response = self._invoke_bedrock(chat_request)

    #     output_message = response["output"]["message"]
    #     input_tokens = response["usage"]["inputTokens"]
    #     output_tokens = response["usage"]["outputTokens"]
    #     finish_reason = response["stopReason"]

    #     chat_response = self._create_response(
    #         model=chat_request.model,
    #         message_id=message_id,
    #         content=output_message["content"],
    #         finish_reason=finish_reason,
    #         input_tokens=input_tokens,
    #         output_tokens=output_tokens,
    #     )
    #     if DEBUG:
    #         logger.info("Proxy response :" + chat_response.model_dump_json())
    #     return chat_response
    
    def chat_stream(self, chat_request: ChatRequest) -> AsyncIterable[bytes]:

        """Default implementation for Chat Stream API"""
        
        response = ''
        message_id = self.generate_message_id()

        if (chat_request.model.startswith(KB_PREFIX)):
            response = self._invoke_kb(chat_request, stream=True)    
        elif (chat_request.model.startswith(AGENT_PREFIX)):
            response = self._invoke_agent(chat_request, stream=True)

            _event_stream = response["completion"]
            
            chunk_count = 1
            message = ChatResponseMessage(
                role="assistant",
                content="",
            )
            stream_response = ChatStreamResponse(
                id=message_id,
                model=chat_request.model,
                choices=[
                    ChoiceDelta(
                        index=0,
                        delta=message,
                        logprobs=None,
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
            yield self.stream_response_to_bytes(stream_response)

            for event in _event_stream:
                chunk_count += 1
                if "chunk" in event:
                    _data = event["chunk"]["bytes"].decode("utf8")
                    message = ChatResponseMessage(content=_data)

                    stream_response = ChatStreamResponse(
                        id=message_id,
                        model=chat_request.model,
                        choices=[
                            ChoiceDelta(
                                index=0,
                                delta=message,
                                logprobs=None,
                                finish_reason=None,
                            )
                        ],
                        usage=None,
                    )
                    yield self.stream_response_to_bytes(stream_response)
                    
                    #message = self._make_fully_cited_answer(_data, event, False, 0)
            
            # return an [DONE] message at the end.
            yield self.stream_response_to_bytes()
            return None
        else:
            response = self._invoke_bedrock(chat_request, stream=True)

        stream = response.get("stream")
        for chunk in stream:
            stream_response = self._create_response_stream(
                model_id=chat_request.model, message_id=message_id, chunk=chunk
            )
            if not stream_response:
                continue
            if DEBUG:
                logger.info("Proxy response :" + stream_response.model_dump_json())
            if stream_response.choices:
                yield self.stream_response_to_bytes(stream_response)
            elif (
                    chat_request.stream_options
                    and chat_request.stream_options.include_usage
            ):
                # An empty choices for Usage as per OpenAI doc below:
                # if you set stream_options: {"include_usage": true}.
                # an additional chunk will be streamed before the data: [DONE] message.
                # The usage field on this chunk shows the token usage statistics for the entire request,
                # and the choices field will always be an empty array.
                # All other chunks will also include a usage field, but with a null value.
                yield self.stream_response_to_bytes(stream_response)

        # return an [DONE] message at the end.
        yield self.stream_response_to_bytes()

    

    # This function invokes knowledgebase
    def _invoke_kb(self, chat_request: ChatRequest, stream=False):
        """Common logic for invoke kb with default model"""
        if DEBUG:
            logger.info("BedrockAgents._invoke_kb: Raw request: " + chat_request.model_dump_json())

        # convert OpenAI chat request to Bedrock SDK request
        args = self._parse_request(chat_request)
        

        if DEBUG:
            logger.info("Bedrock request: " + json.dumps(str(args)))

        # model = self.model_manager.get_all_models()[chat_request.model]
        
        args['modelId'] = DEFAULT_KB_MODEL
        
        kb_id =  chat_request.model.split('-')[1]
        
        ################

        try:
            query = args['messages'][0]['content'][0]['text']
            messages = args['messages']
            query = messages[len(messages)-1]['content'][0]['text']

            # Step 1 - Retrieve Context
            retrieval_request_body = {
                "retrievalQuery": {
                    "text": query
                },
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": 2
                    }
                }
            }
                
            # Make the retrieve request
            response = bedrock_agent_runtime.retrieve(knowledgeBaseId=kb_id, **retrieval_request_body)
            
            # Extract and return the results
            context = ''
            if "retrievalResults" in response:
                for result in response["retrievalResults"]:
                    result = result["content"]["text"]
                    context = f"{context}\n{result}"
                    
                    
            # Step 2 - Append context in the prompt
            args['messages'][0]['content'][0]['text'] = f"Context: {context} \n\n {query}"

            # Step 3 - Make the converse request
            if stream:
                response = bedrock_runtime.converse_stream(**args)
            else:
                response = bedrock_runtime.converse(**args)
        
        except Exception as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=str(e))

        ###############
        return response
    
    # This function invokes knowledgebase
    def _invoke_agent(self, chat_request: ChatRequest, stream=False):
        """Common logic for invoke agent """
        if DEBUG:
            logger.info("BedrockAgents._invoke_agent: Raw request: " + chat_request.model_dump_json())

        # convert OpenAI chat request to Bedrock SDK request
        args = self._parse_request(chat_request)
        

        if DEBUG:
            logger.info("Bedrock request: " + json.dumps(str(args)))

        model = self.model_manager.get_all_models()[chat_request.model]
        
        ################
        
        logger.info("agentId: " + str(model['agent_id']))
        logger.info("alias_id: " + str(model['alias_id']))
        

        try:
            query = args['messages'][0]['content'][0]['text']
            messages = args['messages']
            query = messages[len(messages)-1]['content'][0]['text']
            
            # 呼叫 Agent
            response = bedrock_agent_runtime.invoke_agent(
                agentId= model['agent_id'],
                agentAliasId= model['alias_id'],
                sessionId=chat_request.user,
                inputText=query,
            )
            
            # # Step 1 - Retrieve Context
            # request_params = {
            #     'agentId': "8XMXBLU3PJ",
            #     # 'agentId': model['agent_id'],
            #     'agentAliasId': "H8EA5TLVJF",
            #     # 'agentAliasId': model['alias_id'],
            #     'sessionId': 'unique-session-id',  # Generate a unique session ID
            #     'inputText': query
            # }
                
            # # Make the retrieve request
            # # Invoke the agent
            # response = bedrock_agent_runtime.invoke_agent(**request_params)
            return response
            
        except Exception as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=str(e))
        
    def ini_create_session(self) -> Sesssion :
        try: 
            session_id = str(uuid.uuid4())
            
            Sesssion_response = Sesssion(
                sessionId=session_id,
            )
            return Sesssion_response
        except Exception as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=str(e))
    