"""
Узел сборщика контактов для получения имени и телефона клиента в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history
from ..state import BookingSubState
from ..booking_state_updater import try_update_booking_state_from_reply
from ....services.responses_api.client import ResponsesAPIClient
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger


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

ТВОЯ ФОРМУЛИРОВКА (Используй этот шаблон):
"Хорошо, пожалуйста, напишите ваше имя и номер телефона."
"""
    
    try:
        # Подготавливаем историю для контекста
        # ВАЖНО: Передаем ВСЕ типы сообщений (user, assistant, tool, system) для полного контекста
        input_messages = []
        if history:
            # Берем последние 15 сообщений для контекста (увеличено для лучшего контекста)
            recent_history = history[-15:] if len(history) > 15 else history
            for msg in recent_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                # ВАЖНО: НЕ фильтруем по ролям - передаем ВСЕ типы сообщений
                # Пропускаем только полностью пустые сообщения (без content и без tool_calls)
                # Но для tool сообщений content может быть пустым, но они все равно важны
                if not content and role != "tool":
                    continue
                
                # Добавляем ВСЕ сообщения: user, assistant, tool, system
                msg_dict = {
                    "role": role,
                    "content": content
                }
                # КРИТИЧНО: Для tool сообщений обязательно добавляем tool_call_id
                if role == "tool" and msg.get("tool_call_id"):
                    msg_dict["tool_call_id"] = msg.get("tool_call_id")
                input_messages.append(msg_dict)
        
        # Добавляем последнее сообщение пользователя
        input_messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Создаем клиент и делаем запрос (без инструментов)
        client = ResponsesAPIClient(ResponsesAPIConfig())
        response = client.create_response(
            instructions=system_prompt,
            input_messages=input_messages,
            temperature=0.7,
            max_output_tokens=200
        )
        
        # Получаем ответ от LLM
        reply = response.choices[0].message.content.strip()
        
        logger.info(f"Contact collector ответил: {reply[:100]}...")
        
        # Проверяем, есть ли JSON в ответе для обновления состояния
        updated_extracted_info = try_update_booking_state_from_reply(
            reply=reply,
            current_booking_state=booking_state,
            extracted_info=extracted_info
        )
        
        # КРИТИЧНО: Создаем AIMessage для сохранения в истории LangGraph
        from langchain_core.messages import AIMessage
        new_messages = [AIMessage(content=reply)]
        
        # Если JSON найден и состояние обновлено - не отправляем сообщение клиенту
        if updated_extracted_info:
            logger.info("JSON найден в ответе contact_collector, состояние обновлено, пропускаем отправку сообщения клиенту")
            return {
                "messages": new_messages,
                "answer": "",  # Пустой answer - процесс продолжается автоматически
                "extracted_info": updated_extracted_info
            }
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем сообщение для сохранения в истории
            "answer": reply
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





