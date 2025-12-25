"""
Утилиты для работы с графами
"""
import json
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage


def dicts_to_messages(messages_dicts: List[Dict[str, Any]]) -> List[BaseMessage]:
    """
    Преобразует словари сообщений из orchestrator в объекты BaseMessage для LangGraph
    
    Args:
        messages_dicts: Список словарей с полями role, content, tool_calls, tool_call_id
        
    Returns:
        Список объектов BaseMessage
    """
    langgraph_messages = []
    
    for msg in messages_dicts:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "user":
            langgraph_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            ai_msg = AIMessage(content=content)
            if msg.get("tool_calls"):
                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    if isinstance(tc, dict):
                        func_dict = tc.get("function", {})
                        func_name = func_dict.get("name", "")
                        func_args_str = func_dict.get("arguments", "{}")
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
                        tool_calls.append(tc)
                ai_msg.tool_calls = tool_calls
            langgraph_messages.append(ai_msg)
        elif role == "tool":
            langgraph_messages.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", "")
            ))
        elif role == "system":
            langgraph_messages.append(SystemMessage(content=content))
    
    return langgraph_messages


def messages_to_history(messages: List[BaseMessage | Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Преобразует список BaseMessage объектов или словарей в список словарей для обратной совместимости.
    Сохраняет все типы сообщений, включая ToolMessage с tool_call_id.
    """
    if not messages:
        return []
    
    history = []
    for msg in messages:
        if isinstance(msg, dict):
            msg_dict = {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                msg_dict["tool_call_id"] = msg.get("tool_call_id")
            history.append(msg_dict)
        else:
            role_map = {"ai": "assistant", "system": "system", "tool": "tool", "human": "user"}
            role = role_map.get(getattr(msg, "type", "human"), "user")
            msg_dict = {"role": role, "content": getattr(msg, "content", "")}
            if role == "tool" and hasattr(msg, "tool_call_id"):
                msg_dict["tool_call_id"] = getattr(msg, "tool_call_id", "")
            history.append(msg_dict)
    return history


def _extract_call_manager_messages(messages: List[Dict[str, Any] | BaseMessage]) -> List[Dict[str, Any]]:
    """
    Извлекает все сообщения, связанные с CallManager (AIMessage с tool_calls CallManager и соответствующие ToolMessage)
    
    Args:
        messages: Список сообщений (словари или BaseMessage)
        
    Returns:
        Список сообщений CallManager в формате словарей
    """
    call_manager_messages = []
    call_manager_ids = set()
    
    # Сначала находим все tool_call_id для CallManager
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role")
            tool_calls = msg.get("tool_calls", [])
        else:
            role_map = {"ai": "assistant", "system": "system", "tool": "tool", "human": "user"}
            role = role_map.get(getattr(msg, "type", "human"), "user")
            tool_calls = getattr(msg, "tool_calls", [])
        
        # Проверяем AIMessage с tool_calls
        if role == "assistant" and tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tool_name = tc.get("name", "")
                else:
                    tool_name = getattr(tc, "name", "")
                
                if tool_name == "CallManager":
                    # Сохраняем ID этого tool_call
                    if isinstance(tc, dict):
                        call_id = tc.get("id", "")
                    else:
                        call_id = getattr(tc, "id", "")
                    if call_id:
                        call_manager_ids.add(call_id)
    
    # Теперь собираем все сообщения CallManager
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role")
            tool_calls = msg.get("tool_calls", [])
            tool_call_id = msg.get("tool_call_id", "")
        else:
            role_map = {"ai": "assistant", "system": "system", "tool": "tool", "human": "user"}
            role = role_map.get(getattr(msg, "type", "human"), "user")
            tool_calls = getattr(msg, "tool_calls", [])
            tool_call_id = getattr(msg, "tool_call_id", "") if hasattr(msg, "tool_call_id") else ""
        
        # Добавляем AIMessage с CallManager tool_call
        if role == "assistant" and tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tool_name = tc.get("name", "")
                else:
                    tool_name = getattr(tc, "name", "")
                
                if tool_name == "CallManager":
                    if isinstance(msg, dict):
                        call_manager_messages.append(msg.copy())
                    else:
                        msg_dict = {"role": "assistant", "content": getattr(msg, "content", "")}
                        if tool_calls:
                            msg_dict["tool_calls"] = tool_calls
                        call_manager_messages.append(msg_dict)
                    break
        
        # Добавляем ToolMessage для CallManager
        if role == "tool" and tool_call_id in call_manager_ids:
            if isinstance(msg, dict):
                call_manager_messages.append(msg.copy())
            else:
                msg_dict = {
                    "role": "tool",
                    "content": getattr(msg, "content", ""),
                    "tool_call_id": tool_call_id
                }
                call_manager_messages.append(msg_dict)
    
    return call_manager_messages


def filter_history_for_stage_detector(history: List[Dict[str, Any]], max_messages: int = 10) -> List[Dict[str, Any]]:
    """
    Фильтрует историю для StageDetector:
    - Удаляет сообщения с role: "tool" (кроме CallManager)
    - Ограничивает до последних max_messages сообщений
    - ВАЖНО: Сохраняет CallManager только если он входит в последние max_messages
    
    Args:
        history: История сообщений в формате словарей
        max_messages: Максимальное количество сообщений (по умолчанию 10)
        
    Returns:
        Отфильтрованная и ограниченная история
    """
    if not history:
        return []
    
    # Сначала берем последние max_messages сообщений
    recent_history = history[-max_messages:] if len(history) > max_messages else history
    
    # Извлекаем CallManager сообщения только из последних сообщений
    call_manager_msgs = _extract_call_manager_messages(recent_history)
    call_manager_ids = {msg.get("tool_call_id") for msg in call_manager_msgs if msg.get("role") == "tool"}
    
    # Фильтруем сообщения с role: "tool" (кроме CallManager из последних)
    filtered_history = []
    for msg in recent_history:
        role = msg.get("role", "user")
        tool_call_id = msg.get("tool_call_id", "")
        
        # Пропускаем tool сообщения, кроме CallManager из последних
        if role == "tool" and tool_call_id not in call_manager_ids:
            continue
        
        filtered_history.append(msg)
    
    return filtered_history


def filter_history_conversation_only(messages: List[BaseMessage | Dict[str, Any]], max_messages: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Фильтрует историю, оставляя только переписку (без результатов инструментов):
    - Оставляет только сообщения пользователя (user) и ассистента (assistant)
    - Удаляет все tool messages (результаты инструментов), кроме CallManager
    - Удаляет system messages
    - ВАЖНО: Сохраняет CallManager только если он входит в последние сообщения
    
    Используется в узлах, которым не нужны результаты инструментов из предыдущих этапов.
    
    Args:
        messages: Список BaseMessage объектов или словарей
        max_messages: Максимальное количество сообщений (если None - без ограничения)
        
    Returns:
        Отфильтрованная история только с перепиской (user и assistant) + CallManager из последних сообщений
    """
    if not messages:
        return []
    
    # Если указан лимит, берем последние сообщения
    if max_messages is not None and len(messages) > max_messages:
        recent_messages = messages[-max_messages:]
    else:
        recent_messages = messages
    
    # Извлекаем CallManager сообщения только из последних
    call_manager_msgs = _extract_call_manager_messages(recent_messages)
    call_manager_ids = {msg.get("tool_call_id") for msg in call_manager_msgs if msg.get("role") == "tool"}
    
    history = []
    for msg in recent_messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            tool_call_id = msg.get("tool_call_id", "")
        else:
            role_map = {"ai": "assistant", "system": "system", "tool": "tool", "human": "user"}
            role = role_map.get(getattr(msg, "type", "human"), "user")
            tool_call_id = getattr(msg, "tool_call_id", "") if hasattr(msg, "tool_call_id") else ""
        
        # Оставляем user и assistant сообщения
        if role in ("user", "assistant"):
            if isinstance(msg, dict):
                msg_dict = {"role": role, "content": msg.get("content", "")}
                # Сохраняем tool_calls для assistant (включая CallManager)
                if role == "assistant" and msg.get("tool_calls"):
                    msg_dict["tool_calls"] = msg.get("tool_calls")
            else:
                msg_dict = {"role": role, "content": getattr(msg, "content", "")}
                if role == "assistant" and hasattr(msg, "tool_calls") and msg.tool_calls:
                    msg_dict["tool_calls"] = msg.tool_calls
            history.append(msg_dict)
        # Оставляем tool сообщения только для CallManager из последних
        elif role == "tool" and tool_call_id in call_manager_ids:
            if isinstance(msg, dict):
                msg_dict = {
                    "role": "tool",
                    "content": msg.get("content", ""),
                    "tool_call_id": tool_call_id
                }
            else:
                msg_dict = {
                    "role": "tool",
                    "content": getattr(msg, "content", ""),
                    "tool_call_id": tool_call_id
                }
            history.append(msg_dict)
    
    return history


