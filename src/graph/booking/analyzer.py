"""
Узел анализатора для извлечения сущностей из текста в процессе бронирования
"""
import json
from typing import Dict, Any, Optional
from ..conversation_state import ConversationState
from ..utils import messages_to_history
from .state import BookingSubState
from .booking_state_updater import parse_json_from_response, merge_booking_state
from ...services.responses_api.client import ResponsesAPIClient
from ...services.responses_api.config import ResponsesAPIConfig
from ...services.logger_service import logger


def booking_analyzer_node(state: ConversationState) -> ConversationState:
    """
    Узел анализатора для извлечения сущностей бронирования из текста пользователя
    
    Извлекает:
    - service_id / service_name
    - master_id / master_name
    - slot_time
    - client_name
    - client_phone
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с извлеченными данными в extracted_info
    """
    logger.info("Запуск узла booking_analyzer")
    
    # Получаем текущее сообщение и историю
    last_user_message = state.get("message", "")
    # Преобразуем messages в history для обратной совместимости
    messages = state.get("messages", [])
    history = messages_to_history(messages) if messages else []
    extracted_info = state.get("extracted_info") or {}
    
    # Получаем текущее состояние бронирования из extracted_info
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Логируем текущее состояние для отладки
    logger.debug(f"booking_analyzer: текущее состояние booking_state: {booking_state}")
    
    # Формируем описание текущего состояния для промпта
    current_state_details = _format_current_state(booking_state)
    
    # Формируем промпт для LLM
    system_prompt = f"""Ты — аналитический модуль. Твоя задача — вернуть JSON с обновленными данными на основе диалога.

ТЕКУЩИЕ ДАННЫЕ: {current_state_details}
СООБЩЕНИЕ КЛИЕНТА: {last_user_message}

ПРАВИЛА ИЗВЛЕЧЕНИЯ (Верни JSON):
1. Service ID: Извлекай `service_id` (8 цифр) из инструментов (role="tool"). ТОЛЬКО когда клиент выбрал её для записи. НИКОГДА не придумывай ID. Не извлекай если клиент интересуется деталями услуги, мастерами которые её делают и тд до момента пока он не утвердит эту услугу.
2. Service Name: Если клиент пишет название услуги (текстом, или "хочу стрижку"), верни `service_name`.
3. СМЕНА ТЕМЫ (ВАЖНО): Если клиент меняет желание (например, хотел маникюр, теперь пишет про педикюр) — верни новое `service_name` и установи `service_id`, `master_id`, `slot_time` в null.
4. Slot: Дата/время в формате "YYYY-MM-DD HH:MM" (заполняй только если клиент назвал точное время)
5. Contacts: `client_name` и `client_phone` (только цифры/+).
6. Master: `master_id` (из tool) или `master_name`. (мастер/топ-мастер/юниор не релевантны). Заполняй только если клиент хочет к конкретному мастеру.   

ВАЖНО:
- Верни ТОЛЬКО те поля, которые изменились.
- СМЕНА УСЛУГИ ИЛИ МАСТЕРА: Если клиент хотел записаться на одну услугу (service_id уже заполнен) или к конкретному мастеру (master_id уже заполнен) а потом решил поменять услугу или мастера, ты ОБЯЗАН сбросить `service_id`, `slot_time`, `master_id`, `master_name` в null. Но если меняется услуга на ту, ID которой тебе известно - отправляй правильный ID.

Примеры:
- "Хочу педикюр" (при текущем маникюре) -> {{"service_name": "педикюр", "service_id": null, "slot_time": null}}
- "Меня зовут Аня" -> {{"client_name": "Аня"}}
- "Запиши на завтра в 10" -> {{"slot_time": "2024-12-21 10:00"}}"""

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
            # Это критично для видимости ToolMessage (результаты инструментов) и AIMessage (ответы бота)
            
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
        "content": last_user_message
    })
    
    response_content = None
    try:
        # Создаем клиент и делаем запрос
        client = ResponsesAPIClient(ResponsesAPIConfig())
        
        try:
            response = client.create_response(
                instructions=system_prompt,
                input_messages=input_messages,
                temperature=0.1,  # Низкая температура для более точного извлечения
                max_output_tokens=500
            )
        except Exception as e:
            logger.error(f"Ошибка при запросе к API в analyzer: {e}", exc_info=True)
            return {}
        
        # Получаем ответ от LLM
        if not response or not response.choices:
            logger.error("Пустой response от API в analyzer")
            return {}
        
        message = response.choices[0].message
        
        if message.content is None or not message.content.strip():
            logger.warning("Получен пустой ответ от LLM в booking_analyzer_node")
            # Логируем детали для отладки
            if hasattr(message, 'tool_calls') and message.tool_calls:
                logger.warning(f"Но есть tool_calls: {len(message.tool_calls)}")
            # Возвращаем состояние без изменений при пустом ответе
            return {}
        
        response_content = message.content.strip()
        
        # Парсим JSON из ответа
        extracted_data = parse_json_from_response(response_content)
        if not extracted_data:
            logger.warning("Не удалось распарсить JSON из ответа analyzer")
            return {}
        
        # Обновляем состояние бронирования (не затираем существующие данные None-ами)
        logger.debug(f"booking_analyzer: перед merge_booking_state, booking_state: {booking_state}")
        logger.debug(f"booking_analyzer: extracted_data от LLM: {extracted_data}")
        updated_booking_state = merge_booking_state(booking_state, extracted_data)
        logger.debug(f"booking_analyzer: после merge_booking_state, updated_booking_state: {updated_booking_state}")
        
        # Обновляем extracted_info
        updated_extracted_info = extracted_info.copy()
        updated_extracted_info["booking"] = updated_booking_state
        
        logger.info(f"Извлеченные данные: {extracted_data}")
        logger.info(f"Обновленное состояние бронирования: {updated_booking_state}")
        
        return {
            "extracted_info": updated_extracted_info
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON от LLM: {e}. Ответ: {response_content}")
        # Возвращаем состояние без изменений при ошибке парсинга
        return {}
    except Exception as e:
        logger.error(f"Ошибка в booking_analyzer_node: {e}", exc_info=True)
        # Возвращаем состояние без изменений при ошибке
        return {}


def _format_current_state(booking_state: Dict[str, Any]) -> str:
    """Форматирует текущее состояние для промпта"""
    if not booking_state:
        return "Нет сохраненных данных о бронировании."
    
    parts = []
    if booking_state.get("service_id"):
        parts.append(f"Услуга ID: {booking_state['service_id']}")
    elif booking_state.get("service_name"):
        parts.append(f"Услуга: {booking_state['service_name']}")
    
    if booking_state.get("master_id"):
        parts.append(f"Мастер ID: {booking_state['master_id']}")
    elif booking_state.get("master_name"):
        parts.append(f"Мастер: {booking_state['master_name']}")
    
    if booking_state.get("slot_time"):
        parts.append(f"Время: {booking_state['slot_time']}")
    
    if booking_state.get("client_name"):
        parts.append(f"Имя клиента: {booking_state['client_name']}")
    
    if booking_state.get("client_phone"):
        parts.append(f"Телефон: {booking_state['client_phone']}")
    
    return "\n".join(parts) if parts else "Нет сохраненных данных о бронировании."



