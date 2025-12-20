"""
Узел сборщика контактов для получения имени и телефона клиента в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ..state import BookingSubState
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
    history = state.get("history") or []
    
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
    system_prompt = f"""Ты — AI-администратор салона LookTown. Сейчас этап сбора контактных данных (Шаг 3).
Твой стиль: дружелюбный, профессиональный, краткий.

ТЕКУЩИЕ ДАННЫЕ:
- Дата и время записи: {slot_time_formatted}

ИНСТРУКЦИЯ:
Шаг 3: Сбор данных.
После того как клиент выбрал время, тебе нужно получить его имя и номер телефона (если их нет в текущем состоянии).

ТВОЯ ФОРМУЛИРОВКА (Используй этот шаблон):
"Хорошо, предварительно записываю вас на {slot_time_formatted}. Для подтверждения, пожалуйста, напишите ваше имя и номер телефона."
"""
    
    try:
        # Подготавливаем историю для контекста
        input_messages = []
        if history:
            # Берем последние несколько сообщений для контекста
            recent_history = history[-6:] if len(history) > 6 else history
            input_messages = [
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                }
                for msg in recent_history
                if msg.get("content")
            ]
        
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
        
        return {
            "answer": reply
        }
        
    except Exception as e:
        logger.error(f"Ошибка в contact_collector_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при сборе контактных данных. Попробуйте еще раз."
        }

