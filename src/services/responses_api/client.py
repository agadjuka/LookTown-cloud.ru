"""
Клиент для работы с OpenAI API (cloud.ru)
"""
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .config import ResponsesAPIConfig
from ..logger_service import logger


class ResponsesAPIClient:
    """Клиент для работы с OpenAI API"""
    
    def __init__(self, config: Optional[ResponsesAPIConfig] = None):
        self.config = config or ResponsesAPIConfig()
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
    
    def create_response(
        self,
        instructions: str,
        input_messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        previous_response_id: Optional[str] = None, # Not used in OpenAI chat completions usually
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        """
        Создание запроса к OpenAI API
        """
        try:
            # Формируем сообщения
            messages = []
            
            # System message
            messages.append({
                "role": "system",
                "content": instructions
            })
            
            # History
            if input_messages:
                messages.extend(input_messages)
            
            # Параметры
            params = {
                "model": self.config.model,
                "messages": messages,
                "max_tokens": max_output_tokens if max_output_tokens is not None else self.config.max_tokens,
                "temperature": temperature if temperature is not None else self.config.temperature,
                "top_p": self.config.top_p,
                "presence_penalty": self.config.presence_penalty,
            }
            
            if tools:
                params["tools"] = tools
            
            logger.debug(f"Sending request to OpenAI: {len(messages)} messages")
            
            response = self.client.chat.completions.create(**params)
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при создании запроса к OpenAI API: {e}", exc_info=True)
            raise
