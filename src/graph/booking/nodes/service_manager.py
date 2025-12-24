"""
Узел менеджера услуг для выбора услуги в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, dicts_to_messages
from ..state import BookingSubState
from ..booking_state_updater import try_update_booking_state_from_reply, merge_booking_state
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструменты
from ....agents.tools.get_categories.tool import GetCategories
from ....agents.tools.find_service.tool import FindService
from ....agents.tools.view_service.tool import ViewService
from ....agents.tools.masters.tool import Masters
from ....agents.tools.call_manager import CallManager


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
    
    prompt = f"""You are an AI administrator of the LookTown beauty salon. Currently at the service selection stage.
Your communication style is friendly, professional, brief. Address clients with "вы" (formal you), from a female perspective. Always greet if this is the client's first message. If you need to use a tool, do not respond to the client without using the tool.

YOUR TASK: Help the client choose a service so we get its ID. YOU ARE STRICTLY FORBIDDEN TO ASK THE CLIENT ABOUT TIME FOR BOOKING, CONTACT DETAILS OR SAY THAT YOU BOOKED THEM FOR A SERVICE.
Your main data source: {context_section}
INSTRUCTIONS:
1.1 If the client simply expressed a desire to book or learn about salon services, call `GetCategories` and send the full list from the tool.  
1.2 If the client said which service they want to book, use `FindService`.
1.3 If the client wants to book with a specific master (mentions name and service) — use `FindService` with the `master_name` field specified. If only the name — first clarify the service.

2.1 If the client ask about a service (specific details), use `ViewService`.
2.2 If the client asks about a masters (What types of masters are there, their competence, etc), use `Masters`.

2 If the client chose a specific service (including if you received a list of services from the tool, and only one clearly fits) and did not ask questions about it, return ONLY JSON with the selected service ID in the format: {{"service_id": 12345678}} (the only situation when you can send the service ID)

IMPORTANT:
- Do not write the ID to the client
- Keep the list numbered exactly as you receive it from the tool.
- If the client decided to change the service or master - start over (excluding greeting) according to instructions - call tools again.

If you encounter a system error, don't know the answer to a question, or the client is dissatisfied - call the manager.
"""
    
    return prompt


def service_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера услуг для выбора услуги в процессе бронирования
    
    Этот узел запускается, если service_id в состоянии бронирования все еще None.
    Использует инструменты GetCategories, FindService, ViewService
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
    
    # Получаем данные для контекста
    service_id = booking_state.get("service_id")
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
        tools_registry.register_tool(ViewService)
        tools_registry.register_tool(Masters)
        tools_registry.register_tool(CallManager)
        
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
        
        # Преобразуем новые сообщения из orchestrator в BaseMessage объекты
        new_messages_dicts = result.get("new_messages", [])
        new_messages = dicts_to_messages(new_messages_dicts) if new_messages_dicts else []
        
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
        
        # Проверяем, есть ли JSON в ответе для обновления состояния
        updated_extracted_info = try_update_booking_state_from_reply(
            reply=reply,
            current_booking_state=booking_state,
            extracted_info=extracted_info
        )
        
        # ВАЖНО: Сбрасываем флаг service_details_needed после ответа, чтобы не зациклиться
        if updated_extracted_info:
            # Если JSON был найден, обновляем состояние и сбрасываем флаг
            updated_booking_state = merge_booking_state(
                updated_extracted_info.get("booking", booking_state),
                {"service_details_needed": False}
            )
            updated_extracted_info["booking"] = updated_booking_state
            logger.info("JSON найден в ответе service_manager, состояние обновлено, флаг service_details_needed сброшен")
            return {
                "messages": new_messages,
                "answer": "",  # Пустой answer - процесс продолжается автоматически
                "extracted_info": updated_extracted_info,
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        else:
            # Если JSON не найден, все равно сбрасываем флаг service_details_needed
            updated_booking_state = merge_booking_state(booking_state, {"service_details_needed": False})
            updated_extracted_info = extracted_info.copy()
            updated_extracted_info["booking"] = updated_booking_state
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Service manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        logger.info("Флаг service_details_needed сброшен в False")
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
            "answer": reply,
            "extracted_info": updated_extracted_info,
            "used_tools": used_tools,
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в service_manager_node: {e}", exc_info=True)
        # Даже при ошибке сбрасываем флаг service_details_needed
        updated_booking_state = merge_booking_state(booking_state, {"service_details_needed": False})
        updated_extracted_info = extracted_info.copy()
        updated_extracted_info["booking"] = updated_booking_state
        return {
            "answer": "Извините, произошла ошибка при выборе услуги. Попробуйте еще раз.",
            "extracted_info": updated_extracted_info
        }
