"""
Узел финализатора для создания записи через CreateBooking
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, orchestrator_messages_to_langgraph
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент
from ....agents.tools.create_booking.tool import CreateBooking


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
    # Преобразуем messages в history для обратной совместимости
    messages = state.get("messages", [])
    history = messages_to_history(messages) if messages else []
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
    
    system_prompt = f"""Ты — AI-администратор салона LookTown. Сейчас этап финализации (Шаг 4).

ИНСТРУКЦИЯ:
Шаг 4: Финализируй запись.
Данные собраны. ТЫ ОБЯЗАН ВЫЗВАТЬ инструмент `create_booking` с имеющимися данными.

ДАННЫЕ ДЛЯ ИНСТРУМЕНТА create_booking (используй ТОЧНО эти значения):
- service_id: {service_id} (обязательно, число)
- client_name: "{client_name}" (обязательно, строка)
- client_phone: "{client_phone}" (обязательно, строка)
- datetime: "{slot_time}" (обязательно, формат YYYY-MM-DD HH:MM)
{f'- master_name: "{master_name}" (опционально, только если указан)' if master_name else '- master_name: НЕ УКАЗЫВАЙ этот параметр, если его нет'}

ВАЖНО:
- ОБЯЗАТЕЛЬНО вызови инструмент create_booking ПРЯМО СЕЙЧАС с этими данными.
- После успешного вызова инструмента, подтверди запись клиенту:
  "{confirmation_template}"
  (Склоняй имя мастера, если возможно).
"""
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем инструмент CreateBooking
        tools_registry.register_tool(CreateBooking)
        
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
        
        # КРИТИЧНО: Получаем все новые сообщения из orchestrator (включая AIMessage с tool_calls и ToolMessage)
        new_messages_dicts = result.get("new_messages", [])
        new_messages = orchestrator_messages_to_langgraph(new_messages_dicts) if new_messages_dicts else []
        
        logger.info(f"Finalizer сгенерировал {len(new_messages)} новых сообщений")
        
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

