"""
Узел менеджера услуг для выбора услуги в процессе бронирования
"""
from typing import Dict, Any, Optional, List
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
import json
from ...conversation_state import ConversationState
from ...utils import messages_to_history
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструменты
from ....agents.tools.get_categories.tool import GetCategories
from ....agents.tools.find_service.tool import FindService


def _build_system_prompt(
    service_id: Optional[int],
    service_name: Optional[str],
    master_id: Optional[int],
    master_name: Optional[str]
) -> str:
    """
    Формирует системный промпт для узла service_manager с контекстом
    
    Args:
        service_id: ID услуги (если есть)
        service_name: Название услуги (если есть)
        master_id: ID мастера (если есть)
        master_name: Имя мастера (если есть)
        
    Returns:
        Системный промпт для LLM
    """
    # Формируем секцию КОНТЕКСТ с заполненными полями
    context_parts = []
    
    if service_id is not None:
        context_parts.append(f"- Выбранная услуга ID: {service_id}")
    
    if service_name:
        context_parts.append(f"- Выбранная услуга: {service_name}")
    
    if master_id is not None:
        master_info = f"{master_id}"
        if master_name:
            master_info += f" ({master_name})"
        context_parts.append(f"- Выбранный мастер: {master_info}")
    elif master_name:
        context_parts.append(f"- Выбранный мастер: {master_name}")
    
    # Формируем контекстную секцию
    context_section = ""
    if context_parts:
        context_section = "\nКОНТЕКСТ:\n" + "\n".join(context_parts) + "\n"
    
    prompt = f"""Ты — AI-администратор салона красоты LookTown. Сейчас этап выбора услуги.
Твой стиль общения — дружелюбный, профессиональный, краткий. Общайся на "вы", от женского лица, здоровайся с клиентом, но только один раз.

ТВОЯ ЕДИНСТВЕННАЯ ЗАДАЧА: Помочь клиенту выбрать услугу, чтобы мы получили её ID. ТЕБЕ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО СПРАШИВАТЬ КЛИЕНТА О ВРЕМЕНИ ДЛЯ ЗАПИСИ, КОНТАКТНЫХ ДАННЫХ ИЛИ ГОВОРИТЬ ЧТО ТЫ ЕГО ЗАПИСАЛ НА УСЛУГУ.
Твой главный источник данных: {context_section}
ИНСТРУКЦИЯ:
1.1 Если клиент просто выразил желание записаться или узнать услуги салона, вызови `GetCategories` и отправь полный список из инструмента.  
1.2 Если клиент сказал на какую услугу хочет записаться используй `FindService`.
1.3 Если Клиент хочет записаться к конкретному мастеру (называет имя и услугу) — используй `FindService` с указанием поля `master_name`. Если только имя — сначала уточни услугу.

ВАЖНО:
- Не придумывай услуги и цены. Бери только из инструментов. 
- Всегда вызывай инструмент с заполнение необходимых полей.
- Не пиши клиенту ID
- Сохраняй список нумерованным точо также как получаешь из инструмента.
- Узнать детали об услуге (в т.ч. кто из мастеров её делает - ViewServices)
- Если клиент решил сменить услугу или мастера - начинай сначала (не считая приветствия) по инструкции - вызывай инструменты снова.
"""
    
    return prompt


def _dicts_to_messages(messages_dicts: List[Dict[str, Any]]) -> List:
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


def service_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера услуг для выбора услуги в процессе бронирования
    
    Этот узел запускается, если service_id в состоянии бронирования все еще None.
    Использует инструменты GetCategories, GetServices, FindService
    для помощи клиенту в выборе услуги.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer
    """
    logger.info("Запуск узла service_manager")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Проверяем, есть ли уже service_id
    service_id = booking_state.get("service_id")
    if service_id is not None:
        logger.info(f"Услуга уже выбрана (service_id={service_id}), пропускаем service_manager")
        return {}
    
    # Получаем данные для контекста
    service_name = booking_state.get("service_name")
    master_id = booking_state.get("master_id")
    master_name = booking_state.get("master_name")
    
    # Формируем системный промпт с контекстом
    system_prompt = _build_system_prompt(
        service_id=service_id,
        service_name=service_name,
        master_id=master_id,
        master_name=master_name
    )
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    # Преобразуем messages в history для обратной совместимости
    messages = state.get("messages", [])
    history = messages_to_history(messages) if messages else []
    chat_id = state.get("chat_id")
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем необходимые инструменты
        tools_registry.register_tool(GetCategories)
        tools_registry.register_tool(FindService)
        
        # Создаем orchestrator
        config = ResponsesAPIConfig()
        orchestrator = ResponsesOrchestrator(
            instructions=system_prompt,
            tools_registry=tools_registry,
            config=config
        )
        
        # Запускаем один ход диалога
        result = orchestrator.run_turn(
            user_message=user_message,
            history=history,
            chat_id=chat_id
        )
        
        # Получаем ответ
        reply = result.get("reply", "")
        tool_calls = result.get("tool_calls", [])
        
        # КРИТИЧНО: Преобразуем все новые сообщения из orchestrator в BaseMessage объекты
        new_messages_dicts = result.get("new_messages", [])
        new_messages = _dicts_to_messages(new_messages_dicts) if new_messages_dicts else []
        
        logger.info(f"Service manager сгенерировал {len(new_messages)} новых сообщений")
        # Детальное логирование для отладки ToolMessage
        tool_messages_count = 0
        for i, msg in enumerate(new_messages):
            msg_type = getattr(msg, "type", "unknown")
            content_preview = str(getattr(msg, "content", ""))[:100]
            logger.info(f"  [{i}] Type: {msg_type}, Content: {content_preview}...")
            if msg_type == "tool":
                tool_messages_count += 1
                tool_call_id = getattr(msg, "tool_call_id", "N/A")
                logger.info(f"      ✅ TOOL MESSAGE! tool_call_id={tool_call_id}")
            elif msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                logger.info(f"      ✅ AIMessage с {len(msg.tool_calls)} tool_calls")
        
        if tool_messages_count == 0 and tool_calls:
            logger.warning(f"⚠️ ПРОБЛЕМА: Были tool_calls ({len(tool_calls)}), но нет ToolMessage в new_messages!")
        
        # Проверяем, был ли вызван CallManager
        if result.get("call_manager"):
            logger.info("CallManager был вызван в service_manager_node")
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Service manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
            "answer": reply,
            "used_tools": used_tools,
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в service_manager_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при выборе услуги. Попробуйте еще раз."
        }
