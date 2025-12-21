"""
Узел анализатора для извлечения сущностей из текста в процессе бронирования
"""
import json
from typing import Dict, Any, Optional
from ..conversation_state import ConversationState
from .state import BookingSubState
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
    history = []
    if messages:
        for msg in messages:
            # Если это словарь (старый формат)
            if isinstance(msg, dict):
                history.append({
                    "role": msg.get("role", "user"), 
                    "content": msg.get("content", "")
                })
            # Если это объект LangChain (новый формат)
            else:
                # Маппинг типов LangChain в наши роли
                role = "user"
                if hasattr(msg, "type"):
                    if msg.type == "ai": role = "assistant"
                    elif msg.type == "system": role = "system"
                    elif msg.type == "tool": role = "tool"
                    elif msg.type == "human": role = "user"
                
                history.append({
                    "role": role, 
                    "content": getattr(msg, "content", "")
                })
    extracted_info = state.get("extracted_info") or {}
    
    # Получаем текущее состояние бронирования из extracted_info
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Формируем описание текущего состояния для промпта
    current_state_details = _format_current_state(booking_state)
    
    # Формируем промпт для LLM
    system_prompt = f"""Ты — аналитический модуль. Твоя задача — вернуть JSON с обновленными данными на основе диалога.

ТЕКУЩИЕ ДАННЫЕ: {current_state_details}
СООБЩЕНИЕ КЛИЕНТА: {last_user_message}

ПРАВИЛА ИЗВЛЕЧЕНИЯ (Верни JSON):
1. Service ID: Извлекай `service_id` (8 цифр) ТОЛЬКО из истории сообщений инструментов (role="tool"). НИКОГДА не придумывай ID.
2. Service Name: Если клиент пишет название услуги (текстом, или "хочу стрижку"), верни `service_name`.
3. СМЕНА ТЕМЫ (ВАЖНО): Если клиент меняет желание (например, хотел маникюр, теперь пишет про педикюр) — верни новое `service_name` и установи `service_id`, `master_id`, `slot_time` в null.
4. Slot: Дата/время в формате "YYYY-MM-DD HH:MM" (заполняй только если клиент назвал точное время)
5. Contacts: `client_name` и `client_phone` (только цифры/+).
6. Master: `master_id` (из tool) или `master_name`. (мастер/топ-мастер/юниор не релевантны)

ВАЖНО:
- Верни ТОЛЬКО те поля, которые изменились.
- Если меняется услуга или мастер, ты ОБЯЗАН сбросить `service_id` и `slot_time` в null. Но если меняется услуга на ту, ID которой тебе известно - отправляй правильный ID.

Примеры:
- "Хочу педикюр" (при текущем маникюре) -> {{"service_name": "педикюр", "service_id": null, "slot_time": null}}
- "Меня зовут Аня" -> {{"client_name": "Аня"}}
- "Запиши на завтра в 10" -> {{"slot_time": "2024-12-21 10:00"}}"""

    # Подготавливаем историю для контекста
    input_messages = []
    if history:
        # Берем последние 10 сообщений для контекста
        recent_history = history[-10:] if len(history) > 10 else history
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Пропускаем system сообщения (Tools used, EXTRACTED_INFO и т.д.)
            if role == "system":
                continue
            
            # Пропускаем пустые сообщения
            if not content:
                continue
            
            # Для tool сообщений - включаем их в контекст, чтобы analyzer видел результаты инструментов
            # Это поможет извлечь service_id из результатов GetServices и других инструментов
            if role == "tool":
                # Tool сообщения содержат результаты инструментов в формате:
                # "Tool: <name>\nArgs: {...}\nResult: ..."
                # Это полезная информация для извлечения данных
                input_messages.append({
                    "role": role,
                    "content": content
                })
            else:
                # Для остальных ролей (user, assistant) - добавляем как обычно
                input_messages.append({
                    "role": role,
                    "content": content
                })
    
    # Добавляем последнее сообщение пользователя
    input_messages.append({
        "role": "user",
        "content": last_user_message
    })
    
    response_content = None
    try:
        # Создаем клиент и делаем запрос
        client = ResponsesAPIClient(ResponsesAPIConfig())
        response = client.create_response(
            instructions=system_prompt,
            input_messages=input_messages,
            temperature=0.1,  # Низкая температура для более точного извлечения
            max_output_tokens=500
        )
        
        # Получаем ответ от LLM
        message = response.choices[0].message
        if message.content is None:
            logger.warning("Получен пустой ответ от LLM в booking_analyzer_node")
            # Возвращаем состояние без изменений при пустом ответе
            return {}
        
        response_content = message.content.strip()
        logger.debug(f"Ответ LLM от analyzer: {response_content}")
        
        # Парсим JSON из ответа
        extracted_data = _parse_llm_response(response_content)
        
        # Обновляем состояние бронирования (не затираем существующие данные None-ами)
        updated_booking_state = _merge_booking_state(booking_state, extracted_data)
        
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


def _parse_llm_response(response_content: str) -> Dict[str, Any]:
    """
    Парсит ответ LLM и извлекает JSON
    
    Пытается найти JSON в ответе, даже если он обернут в markdown или текст
    """
    response_content = response_content.strip()
    
    # Убираем markdown code blocks если есть
    if response_content.startswith("```"):
        lines = response_content.split("\n")
        # Убираем первую строку (```json или ```)
        if len(lines) > 1:
            response_content = "\n".join(lines[1:])
        # Убираем последнюю строку (```)
        if response_content.endswith("```"):
            response_content = response_content[:-3].strip()
    
    try:
        return json.loads(response_content)
    except json.JSONDecodeError:
        # Пытаемся найти JSON в тексте
        start_idx = response_content.find("{")
        end_idx = response_content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response_content[start_idx:end_idx + 1]
            return json.loads(json_str)
        # Если не нашли, возвращаем пустой словарь
        logger.warning(f"Не удалось распарсить JSON из ответа: {response_content}")
        return {}


def _merge_booking_state(
    current_state: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Объединяет текущее состояние с извлеченными данными
    
    Логика обновления:
    1. Если LLM вернула None для service_id (смена темы) - жесткий сброс связанных полей
    2. Обычное обновление остальных полей (только не-None значения)
    """
    # Копируем текущее состояние
    current_details = current_state.copy()
    
    # 1. Если LLM вернула null для service_id (значит, была смена темы)
    if "service_id" in extracted_data and extracted_data["service_id"] is None:
        # Жесткий сброс всего, что связано с услугой
        current_details["service_id"] = None
        current_details["slot_time"] = None
        current_details["slot_time_verified"] = None
        current_details["master_id"] = None
        current_details.pop("master_name", None)  # Удаляем, если есть
    
    # Если slot_time сбрасывается явно, сбрасываем и slot_time_verified
    if "slot_time" in extracted_data and extracted_data["slot_time"] is None:
        current_details["slot_time_verified"] = None
    
    # 2. Обычное обновление остальных полей
    for key, value in extracted_data.items():
        # Если значение пришло (даже если это новое имя услуги) - обновляем
        if value is not None:
            # Валидация и преобразование типов для числовых полей
            if key == "service_id":
                # Преобразуем service_id в int, если это строка
                try:
                    if isinstance(value, str):
                        current_details[key] = int(value)
                    elif isinstance(value, int):
                        current_details[key] = value
                    else:
                        logger.warning(f"Неверный тип service_id: {type(value)}, значение: {value}")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"Не удалось преобразовать service_id в int: {value}, ошибка: {e}")
                    continue
            elif key == "master_id":
                # Преобразуем master_id в int, если это строка
                try:
                    if isinstance(value, str):
                        current_details[key] = int(value)
                    elif isinstance(value, int):
                        current_details[key] = value
                    else:
                        logger.warning(f"Неверный тип master_id: {type(value)}, значение: {value}")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"Не удалось преобразовать master_id в int: {value}, ошибка: {e}")
                    continue
            else:
                current_details[key] = value
        # Если value is None, мы это уже обработали выше для спец. полей,
        # либо игнорируем для остальных, чтобы не стереть случайно
    
    return current_details

