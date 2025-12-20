"""
Узел анализатора для извлечения сущностей из текста в процессе бронирования
"""
import json
from typing import Dict, Any, Optional
from ..conversation_state import ConversationState
from .state import BookingSubState, DialogStep
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
    history = state.get("history") or []
    extracted_info = state.get("extracted_info") or {}
    
    # Получаем текущее состояние бронирования из extracted_info
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Формируем описание текущего состояния для промпта
    current_state_details = _format_current_state(booking_state)
    
    # Формируем промпт для LLM
    system_prompt = f"""Ты — аналитический модуль. Твоя задача — извлечь данные о бронировании из диалога.

ТЕКУЩИЕ ДАННЫЕ В СИСТЕМЕ:
{current_state_details}

ПОСЛЕДНЕЕ СООБЩЕНИЕ КЛИЕНТА: {last_user_message}

ТВОЯ ЦЕЛЬ: Вернуть ТОЛЬКО валидный JSON с обновленными полями.
1. Если клиент явно выбирает услугу (например, 'Хочу вторую', 'Запиши на стрижку'), и ты можешь понять ID из контекста истории или названия — извлеки `service_id` (состоит из 8 цифр, не путай с номерами в списках) (int) или хотя бы `service_name` (str).
   ВАЖНО: Если в истории есть результаты инструментов (сообщения с role="tool"), используй их для извлечения service_id. 
2. Если клиент называет дату/время — извлеки `slot_time` в формате "YYYY-MM-DD HH:MM" (например, "2024-12-25 14:30").
3. Если клиент называет имя — извлеки `client_name` (str).
4. Если клиент называет телефон — извлеки `client_phone` (str, только цифры или с +).
5. Если клиент выбирает мастера — извлеки `master_id` (int) или `master_name` (str). (мастер/топ мастер/юниор не являются ID или именем, это категории услуг, используй их для выбора услуги)
6. Если клиент передумал и начал запись на другую услугу - начинай заново.

ВАЖНО:
- Верни ТОЛЬКО JSON объект с полями, которые ты извлек или обновил.
- Не включай поля, которые не изменились или не были упомянуты.
- Если поле не найдено в сообщении, не включай его в ответ.
- Используй результаты инструментов из истории (сообщения с role="tool") для извлечения точных ID услуг, мастеров и другой информации.
- Формат ответа: {{"service_id": 1, "client_name": "Аня", "client_phone": "89991234567"}} или {{}} если ничего не найдено.

Примеры:
- "Меня зовут Аня, телефон 89991234567" → {{"client_name": "Аня", "client_phone": "89991234567"}}
- "Хочу записаться на стрижку" → {{"service_name": "стрижка"}}
- "25 декабря в 14:30" → {{"slot_time": "2024-12-25 14:30"}}
- Клиент не видит ID, он пишет название текстом, или номер из списка, или категорию (мастер/топ мастер/юниор). Ты должен найти ID из ToolResult. Клиент не будет писать точное название, ты должен понять что он имеет ввиду."""

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
        response_content = response.choices[0].message.content.strip()
        logger.debug(f"Ответ LLM от analyzer: {response_content}")
        
        # Парсим JSON из ответа
        extracted_data = _parse_llm_response(response_content)
        
        # Обновляем состояние бронирования (не затираем существующие данные None-ами)
        updated_booking_state = _merge_booking_state(booking_state, extracted_data)
        
        # Обновляем dialog_step на основе заполненности данных
        updated_booking_state["dialog_step"] = _determine_dialog_step(updated_booking_state)
        
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
    
    if booking_state.get("dialog_step"):
        parts.append(f"Шаг диалога: {booking_state['dialog_step']}")
    
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
    
    При перезаписи ключевых полей очищает зависимые поля:
    - При перезаписи service_id/service_name → очищает master_id, master_name, slot_time, client_name, client_phone
    - При перезаписи master_id/master_name → очищает slot_time, client_name, client_phone
    - При перезаписи slot_time → очищает client_name, client_phone
    - При перезаписи client_name → очищает client_phone
    - При перезаписи client_phone → очищает client_name
    """
    merged = current_state.copy()
    
    # Определяем, какие поля были перезаписаны
    service_changed = False
    master_changed = False
    slot_changed = False
    name_changed = False
    phone_changed = False
    
    for key, value in extracted_data.items():
        # Обновляем только если значение не None и не пустое
        if value is not None and value != "":
            # Проверяем, было ли это поле изменено (значение отличается от текущего)
            current_value = merged.get(key)
            if current_value != value:
                merged[key] = value
                
                # Отмечаем, какие поля были изменены
                if key in ("service_id", "service_name"):
                    service_changed = True
                elif key in ("master_id", "master_name"):
                    master_changed = True
                elif key == "slot_time":
                    slot_changed = True
                elif key == "client_name":
                    name_changed = True
                elif key == "client_phone":
                    phone_changed = True
            else:
                # Значение не изменилось, просто обновляем
                merged[key] = value
    
    # Очищаем зависимые поля при перезаписи ключевых
    if service_changed:
        # При изменении услуги очищаем все зависимые поля
        # Также очищаем парное поле услуги (если меняется service_id, очищаем service_name и наоборот)
        # Это нужно, чтобы избежать конфликтов между старым ID и новым названием
        if "service_id" in extracted_data:
            # Если обновляется service_id, очищаем service_name (если он не был обновлен)
            if "service_name" not in extracted_data:
                merged.pop("service_name", None)
        if "service_name" in extracted_data:
            # Если обновляется service_name, очищаем service_id (если он не был обновлен)
            if "service_id" not in extracted_data:
                merged.pop("service_id", None)
        
        # Очищаем все зависимые поля (мастер, время, контакты)
        merged.pop("master_id", None)
        merged.pop("master_name", None)
        merged.pop("slot_time", None)
        merged.pop("client_name", None)
        merged.pop("client_phone", None)
    elif master_changed:
        # При изменении мастера очищаем время и контакты
        merged.pop("slot_time", None)
        merged.pop("client_name", None)
        merged.pop("client_phone", None)
    elif slot_changed:
        # При изменении времени очищаем контакты
        merged.pop("client_name", None)
        merged.pop("client_phone", None)
    elif name_changed:
        # При изменении имени очищаем телефон
        merged.pop("client_phone", None)
    elif phone_changed:
        # При изменении телефона очищаем имя
        merged.pop("client_name", None)
    
    return merged


def _determine_dialog_step(booking_state: Dict[str, Any]) -> str:
    """
    Определяет текущий шаг диалога на основе заполненности данных
    """
    has_service = booking_state.get("service_id") or booking_state.get("service_name")
    has_slot = booking_state.get("slot_time")
    has_contacts = booking_state.get("client_name") and booking_state.get("client_phone")
    
    if not has_service:
        return DialogStep.SERVICE.value
    elif not has_slot:
        return DialogStep.SLOT.value
    elif not has_contacts:
        return DialogStep.CONTACTS.value
    else:
        return DialogStep.CONFIRMATION.value

