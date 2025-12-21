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


def orchestrator_messages_to_langgraph(
    messages: List[Dict[str, Any]]
) -> List[BaseMessage]:
    """
    Преобразует сообщения из формата orchestrator (словари) в формат LangGraph (BaseMessage).
    
    КРИТИЧНО: Эта функция преобразует все типы сообщений, включая:
    - AIMessage с tool_calls (вызовы инструментов)
    - ToolMessage (результаты работы инструментов)
    - HumanMessage (сообщения пользователя)
    
    Args:
        messages: Список словарей с полями role, content, tool_calls, tool_call_id
        
    Returns:
        Список объектов BaseMessage для LangGraph
    """
    langgraph_messages = []
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "user":
            langgraph_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            ai_msg = AIMessage(content=content)
            # КРИТИЧНО: Сохраняем tool_calls, если они есть
            if msg.get("tool_calls"):
                # Преобразуем tool_calls в формат LangChain
                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    if isinstance(tc, dict):
                        # Формат из OpenAI SDK: {"id": "...", "type": "function", "function": {...}}
                        func_dict = tc.get("function", {})
                        func_name = func_dict.get("name", "")
                        func_args_str = func_dict.get("arguments", "{}")
                        
                        # Парсим arguments из JSON строки
                        import json
                        try:
                            func_args = json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                        except json.JSONDecodeError:
                            func_args = {}
                        
                        tool_calls.append({
                            "name": func_name,
                            "args": func_args,
                            "id": tc.get("id", ""),
                        })
                    else:
                        # Уже в формате LangChain
                        tool_calls.append(tc)
                ai_msg.tool_calls = tool_calls
            langgraph_messages.append(ai_msg)
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            langgraph_messages.append(ToolMessage(
                content=content,
                tool_call_id=tool_call_id
            ))
        elif role == "system":
            langgraph_messages.append(SystemMessage(content=content))
    
    return langgraph_messages

