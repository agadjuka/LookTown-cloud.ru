"""
Узел сборщика контактов для получения имени и телефона клиента в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, dicts_to_messages
from ..state import BookingSubState
from ..booking_state_updater import try_update_booking_state_from_reply
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент
from ....agents.tools.call_manager import CallManager


def contact_collector_node(state: ConversationState) -> ConversationState:
    """
    Узел сборщика контактов для получения имени и телефона клиента
    
    Этот узел запускается, когда service_id и slot_time уже есть,
    но отсутствует client_name или client_phone.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer
    """
    logger.info("Запуск узла contact_collector")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Проверяем, что есть service_id и slot_time
    service_id = booking_state.get("service_id")
    slot_time = booking_state.get("slot_time")
    
    if service_id is None or slot_time is None:
        logger.error("contact_collector_node вызван без service_id или slot_time - это ошибка логики графа")
        return {
            "answer": "Извините, произошла ошибка. Пожалуйста, начните бронирование заново."
        }
    
    # Проверяем, чего не хватает
    client_name = booking_state.get("client_name")
    client_phone = booking_state.get("client_phone")
    
    # Если все данные уже есть, пропускаем этот узел
    if client_name and client_phone:
        logger.info("Контактные данные уже собраны, пропускаем contact_collector")
        return {}
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    # Преобразуем messages в history для обратной совместимости
    messages = state.get("messages", [])
    history = messages_to_history(messages) if messages else []
    
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
    system_prompt = f"""Ты — AI-администратор салона LookTown. 
Твой стиль: дружелюбный, профессиональный, краткий.

ТЕКУЩИЕ ДАННЫЕ:
- Дата и время записи: {slot_time_formatted}

ИНСТРУКЦИЯ:
Тебе нужно получить имя и номер телефона клиента.

Примерная формулировка: Хорошо, пожалуйста, напишите ваше имя и номер телефона. (можешь менять в зависимости от ситуации)

Если ты сталкиваешься с системной ошибкой, не знаешь ответа на вопрос или клиент чем то недоволен - зови менеджера.
"""
    
    try:
        # Получаем chat_id
        chat_id = state.get("chat_id")
        
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем инструмент CallManager
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
            logger.info("CallManager был вызван в contact_collector_node")
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        logger.info(f"Contact collector ответил: {reply[:100]}...")
        
        # Проверяем, есть ли JSON в ответе для обновления состояния
        updated_extracted_info = try_update_booking_state_from_reply(
            reply=reply,
            current_booking_state=booking_state,
            extracted_info=extracted_info
        )
        
        # Если JSON найден и состояние обновлено - не отправляем сообщение клиенту
        if updated_extracted_info:
            logger.info("JSON найден в ответе contact_collector, состояние обновлено, пропускаем отправку сообщения клиенту")
            return {
                "messages": new_messages,
                "answer": "",  # Пустой answer - процесс продолжается автоматически
                "extracted_info": updated_extracted_info,
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
            "answer": reply,
            "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в contact_collector_node: {e}", exc_info=True)
        error_message = "Извините, произошла ошибка при сборе контактных данных. Попробуйте еще раз."
        # КРИТИЧНО: Создаем AIMessage даже при ошибке для сохранения в истории
        from langchain_core.messages import AIMessage
        new_messages = [AIMessage(content=error_message)]
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем сообщение для сохранения в истории
            "answer": error_message
        }





