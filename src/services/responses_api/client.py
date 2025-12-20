"""
Клиент для работы с OpenAI API (cloud.ru)
"""
import json
import re
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
    
    def _normalize_text(self, text: str) -> str:
        """
        Нормализует текст для отправки в API
        
        Убирает проблемные символы и форматирование, которые могут вызвать ошибки
        """
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        
        # Убираем нулевые байты и другие проблемные символы
        text = text.replace('\x00', '')
        
        # Нормализуем переносы строк
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Убираем множественные пробелы (но сохраняем переносы строк)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Убираем пробелы в начале и конце каждой строки
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)
        
        # Убираем множественные пустые строки
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Убираем управляющие символы, кроме стандартных (табуляция, перенос строки)
        text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
        
        return text.strip()
    
    def _normalize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализует сообщение для отправки в API
        """
        normalized = {
            "role": message.get("role", "user"),
            "content": self._normalize_text(message.get("content", ""))
        }
        
        # Сохраняем tool_calls если есть
        if "tool_calls" in message:
            normalized["tool_calls"] = message["tool_calls"]
        
        # Сохраняем tool_call_id если есть
        if "tool_call_id" in message:
            normalized["tool_call_id"] = message["tool_call_id"]
        
        return normalized
    
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
            # Нормализуем instructions
            normalized_instructions = self._normalize_text(instructions)
            
            # Формируем сообщения
            messages = []
            
            # System message
            messages.append({
                "role": "system",
                "content": normalized_instructions
            })
            
            # History - нормализуем каждое сообщение
            if input_messages:
                for msg in input_messages:
                    normalized_msg = self._normalize_message(msg)
                    # Пропускаем пустые сообщения
                    if normalized_msg.get("content") or normalized_msg.get("tool_calls"):
                        messages.append(normalized_msg)
            
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
            logger.debug(f"Instructions length: {len(normalized_instructions)} chars")
            
            response = self.client.chat.completions.create(**params)
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при создании запроса к OpenAI API: {e}", exc_info=True)
            logger.error(f"Instructions (first 500 chars): {instructions[:500] if instructions else 'None'}")
            raise
