"""
Узел анализатора для извлечения сущностей из текста в процессе бронирования
"""
import json
from datetime import datetime
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
    system_prompt = f"""You are an analytical module. Your task is to return JSON with updated data based on the dialogue.

CURRENT DATA: {current_state_details}
CLIENT MESSAGE: {last_user_message}

EXTRACTION RULES (Return JSON):
1. Service ID: Extract `service_id` (8 digits) from tools (role="tool"). ONLY when the client chose it for booking. NEVER make up IDs. Do not extract if the client is interested in service details, masters who perform it, etc. until they confirm this service.
2. Service Name: If the client writes a service name (as text, or "хочу стрижку"), return `service_name`.
3. TOPIC CHANGE (IMPORTANT): If the client changes their desire (e.g., wanted a manicure, now writes about a pedicure) — return the new `service_name` and set `service_id`, `master_id`, `slot_time` to null.
4. Slot: Date/time in format "YYYY-MM-DD HH:MM" (fill only if the client named an exact time)
5. Contacts: `client_name` and `client_phone` (digits/+ only).
6. Master: `master_id` (from tool) or `master_name`. (мастер/топ-мастер/юниор are not relevant). Fill only if the client wants a specific master.   

Exception: If the client wants to learn details about a service (asks for details of any service), master (interested in the master who performs this service), masters who perform the service then: Add the field `"service_details_needed": true` to JSON (do not do this when the client wants to book). If user already got info about services/masters, and want book - dont add it.

IMPORTANT:
- Return ONLY the fields that have changed.
- SERVICE OR MASTER CHANGE: If the client wanted to book one service (service_id already filled) or with a specific master (master_id already filled) and then decided to change the service or master, you MUST reset `service_id`, `slot_time`, `master_id`, `master_name` to null. But if the service changes to one whose ID you know - send the correct ID.

Examples:
- "Хочу педикюр" (with current manicure) -> {{"service_name": "педикюр", "service_id": null, "slot_time": null}}
- "Меня зовут Аня" -> {{"client_name": "Аня"}}
- "Запиши на завтра в 10" -> {{"slot_time": "2024-12-21 10:00"}}

If you encounter a system error, don't know the answer to a question, or the client is dissatisfied - call the manager (if you already called the manager, don't call it again, continue the conversation).
."""

    # Подготавливаем историю для контекста
    # ВАЖНО: Передаем ВСЕ типы сообщений (user, assistant, tool, system) для полного контекста
    # ВАЖНО: Сохраняем CallManager только если он входит в последние 10 сообщений
    input_messages = []
    if history:
        # Берем последние 10 сообщений для контекста
        # CallManager будет включен, если он входит в эти 10 сообщений
        recent_history = history[-10:] if len(history) > 10 else history
        
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
    
    # Добавляем последнее сообщение пользователя только если его еще нет в истории
    # Проверяем, не является ли последнее сообщение в истории уже текущим сообщением
    last_message_is_current = (
        input_messages and 
        input_messages[-1].get("role") == "user" and 
        input_messages[-1].get("content") == last_user_message
    )
    
    if not last_message_is_current:
        input_messages.append({
            "role": "user",
            "content": last_user_message
        })
    
    response_content = None
    try:
        # Создаем клиент и делаем запрос
        config = ResponsesAPIConfig()
        client = ResponsesAPIClient(config)
        
        try:
            response = client.create_response(
                instructions=system_prompt,
                input_messages=input_messages
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
        
        # Проверяем, если slot_time имеет время 00:00, то не устанавливаем slot_time
        # (это означает, что указана только дата, без времени)
        if "slot_time" in extracted_data and extracted_data["slot_time"]:
            slot_time = extracted_data["slot_time"]
            if _is_midnight_time(slot_time):
                logger.info(f"Обнаружено время 00:00 в slot_time={slot_time}, обрабатываем как дату без времени")
                # Удаляем slot_time из extracted_data, чтобы не устанавливать его
                extracted_data.pop("slot_time")
        
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


def _is_midnight_time(slot_time: str) -> bool:
    """
    Проверяет, является ли время в slot_time полночью (00:00)
    
    Args:
        slot_time: Время в формате "YYYY-MM-DD HH:MM"
        
    Returns:
        True, если время равно 00:00, иначе False
    """
    try:
        dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
        return dt.hour == 0 and dt.minute == 0
    except (ValueError, AttributeError):
        return False


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



