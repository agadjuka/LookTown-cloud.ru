"""
Утилиты для работы с графами
"""
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage


def messages_to_history(messages: List[BaseMessage | Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Преобразует список BaseMessage объектов или словарей в список словарей для обратной совместимости.
    
    КРИТИЧНО: Сохраняет все типы сообщений, включая ToolMessage с tool_call_id.
    
    Args:
        messages: Список объектов BaseMessage или словарей
        
    Returns:
        Список словарей с полями role, content и tool_call_id (для ToolMessage)
    """
    history = []
    if messages:
        for msg in messages:
            # Если это словарь (старый формат)
            if isinstance(msg, dict):
                msg_dict = {
                    "role": msg.get("role", "user"), 
                    "content": msg.get("content", "")
                }
                # КРИТИЧНО: Сохраняем tool_call_id для ToolMessage
                if msg.get("role") == "tool" and msg.get("tool_call_id"):
                    msg_dict["tool_call_id"] = msg.get("tool_call_id")
                history.append(msg_dict)
            # Если это объект LangChain (новый формат)
            else:
                # Маппинг типов LangChain в наши роли
                role = "user"
                if hasattr(msg, "type"):
                    if msg.type == "ai": role = "assistant"
                    elif msg.type == "system": role = "system"
                    elif msg.type == "tool": role = "tool"
                    elif msg.type == "human": role = "user"
                
                msg_dict = {
                    "role": role, 
                    "content": getattr(msg, "content", "")
                }
                # КРИТИЧНО: Сохраняем tool_call_id для ToolMessage
                if role == "tool" and hasattr(msg, "tool_call_id"):
                    msg_dict["tool_call_id"] = getattr(msg, "tool_call_id", "")
                
                history.append(msg_dict)
    return history


