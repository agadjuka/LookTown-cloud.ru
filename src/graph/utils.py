"""
Утилиты для работы с графами
"""
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage


def messages_to_history(messages: List[BaseMessage | Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Преобразует список BaseMessage объектов или словарей в список словарей для обратной совместимости.
    
    Args:
        messages: Список объектов BaseMessage или словарей
        
    Returns:
        Список словарей с полями role и content
    """
    history = []
    if messages:
        for msg in messages:
            # Если это словарь (старый формат)
            if isinstance(msg, dict):
                history.append({
                    "role": msg.get("role", "user"), 
                    "content": msg.get("content", "")
                })
            # Если это объект LangChain (новый формат)
            else:
                # Маппинг типов LangChain в наши роли
                role = "user"
                if hasattr(msg, "type"):
                    if msg.type == "ai": role = "assistant"
                    elif msg.type == "system": role = "system"
                    elif msg.type == "tool": role = "tool"
                    elif msg.type == "human": role = "user"
                
                history.append({
                    "role": role, 
                    "content": getattr(msg, "content", "")
                })
    return history

