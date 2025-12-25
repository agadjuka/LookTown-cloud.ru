"""
Узел финализатора для создания записи через CreateBooking
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, dicts_to_messages, filter_history_conversation_only
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент
from ....agents.tools.create_booking.tool import CreateBooking
from ....agents.tools.call_manager import CallManager


def finalizer_node(state: ConversationState) -> ConversationState:
    """
    Узел финализатора для создания записи через CreateBooking
    
    Этот узел запускается, когда все данные собраны:
    service_id, slot_time, client_name, client_phone.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer и обновленным is_finalized
    """
    logger.info("Запуск узла finalizer")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Проверяем наличие всех необходимых данных
    service_id = booking_state.get("service_id")
    slot_time = booking_state.get("slot_time")
    client_name = booking_state.get("client_name")
    client_phone = booking_state.get("client_phone")
    master_name = booking_state.get("master_name")
    
    # Проверяем, что все обязательные данные есть
    if not service_id or not slot_time or not client_name or not client_phone:
        missing = []
        if not service_id:
            missing.append("service_id")
        if not slot_time:
            missing.append("slot_time")
        if not client_name:
            missing.append("client_name")
        if not client_phone:
            missing.append("client_phone")
        logger.error(f"finalizer_node вызван без обязательных данных: {missing}")
        return {
            "answer": "Извините, произошла ошибка. Не все данные собраны. Пожалуйста, начните бронирование заново."
        }
    
    # Проверяем, не финализировано ли уже
    if booking_state.get("is_finalized"):
        logger.info("Бронирование уже финализировано, пропускаем finalizer")
        return {}
    
    # Получаем название услуги для промпта (если есть)
    service_name = booking_state.get("service_name", "услуга")
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    # Фильтруем историю: оставляем только переписку (user и assistant), без tool messages
    messages = state.get("messages", [])
    history = filter_history_conversation_only(messages) if messages else []
    chat_id = state.get("chat_id")
    
    # Форматируем дату и время для промпта
    try:
        from datetime import datetime
        dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
        formatted_date = dt.strftime("%d.%m.%Y")
        formatted_time = dt.strftime("%H:%M")
        slot_time_formatted = f"{formatted_date} в {formatted_time}"
    except:
        slot_time_formatted = slot_time
    
    # Формируем системный промпт согласно ТЗ
    master_info_text = f" к мастеру {master_name}" if master_name else ""
    confirmation_template = f"Готово! Я записала вас на {service_name} {slot_time_formatted}{master_info_text}. Будем вас ждать!"
    
    system_prompt = f"""You are an AI administrator of the LookTown salon. Currently at the finalization stage (Step 4).

INSTRUCTION:
 YOU MUST CALL the `create_booking` tool with the available data.

DATA FOR create_booking TOOL (use EXACTLY these values):
- service_id: {service_id} (required, number)
- client_name: "{client_name}" (required, string)
- client_phone: "{client_phone}" (required, string)
- datetime: "{slot_time}" (required, format YYYY-MM-DD HH:MM)
{f'- master_name: "{master_name}" (optional, only if specified)' if master_name else '- master_name: DO NOT specify this parameter if it is not available'}

IMPORTANT:
- MANDATORY call the create_booking tool RIGHT NOW with this data.

  (Decline the master's name if possible).

If you encounter a system error, don't know the answer to a question, or the client is dissatisfied - call the manager (if you already called the manager, don't call it again, continue the conversation).
.
"""
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем инструмент CreateBooking
        tools_registry.register_tool(CreateBooking)
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
            logger.info("CallManager был вызван в finalizer_node")
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Проверяем, был ли вызван CreateBooking
        create_booking_called = any(
            tc.get("name") == "CreateBooking" for tc in (tool_calls or [])
        )
        
        if create_booking_called:
            # Обновляем состояние: устанавливаем флаг is_finalized
            updated_booking_state = booking_state.copy()
            updated_booking_state["is_finalized"] = True
            
            updated_extracted_info = extracted_info.copy()
            updated_extracted_info["booking"] = updated_booking_state
            
            logger.info("CreateBooking был вызван, устанавливаем is_finalized=True")
            
            # Формируем список использованных инструментов
            used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
            
            logger.info(f"Finalizer ответил: {reply[:100]}...")
            logger.info(f"Использованные инструменты: {used_tools}")
            
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
                "answer": reply,
                "used_tools": used_tools,
                "tool_results": tool_calls if tool_calls else [],
                "extracted_info": updated_extracted_info
            }
        else:
            # Если CreateBooking не был вызван, возвращаем ответ как есть
            # (возможно, LLM еще обрабатывает или есть ошибка)
            logger.warning("CreateBooking не был вызван в finalizer_node")
            used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
            
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": reply,
                "used_tools": used_tools,
                "tool_results": tool_calls if tool_calls else []
            }
        
    except Exception as e:
        logger.error(f"Ошибка в finalizer_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при создании записи. Попробуйте еще раз."
        }

