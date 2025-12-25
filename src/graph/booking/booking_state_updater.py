"""
Общие функции для обновления состояния бронирования из JSON ответов LLM
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
from ...services.logger_service import logger


def parse_json_from_response(response_content: str) -> Optional[Dict[str, Any]]:
    """
    Парсит JSON из ответа LLM
    
    Пытается найти JSON в ответе, даже если он обернут в markdown или текст
    
    Args:
        response_content: Текст ответа от LLM
        
    Returns:
        Распарсенный JSON словарь или None, если JSON не найден
    """
    if not response_content or not response_content.strip():
        return None
    
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
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        # Если не нашли, возвращаем None
        return None


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


def merge_booking_state(
    current_state: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Объединяет текущее состояние с извлеченными данными
    
    Логика обновления:
    1. Если LLM вернула None для service_id (смена темы) - жесткий сброс связанных полей
    2. Если slot_time имеет время 00:00 - не устанавливаем slot_time (это дата без времени)
    3. Если slot_time сбрасывается явно (None) - сбрасываем и slot_time_verified
    4. Если master_id сбрасывается явно (None) - сбрасываем и master_name
    5. Если master_name сбрасывается явно (None) - удаляем master_name
    6. Обычное обновление остальных полей (только не-None значения)
    
    Args:
        current_state: Текущее состояние бронирования
        extracted_data: Новые данные из JSON ответа LLM
        
    Returns:
        Обновленное состояние бронирования
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
    
    # 2. Если slot_time имеет время 00:00, не устанавливаем slot_time
    if "slot_time" in extracted_data and extracted_data["slot_time"]:
        if _is_midnight_time(extracted_data["slot_time"]):
            logger.info(f"Обнаружено время 00:00 в slot_time={extracted_data['slot_time']}, не устанавливаем slot_time")
            # Удаляем slot_time из extracted_data, чтобы не устанавливать его
            extracted_data.pop("slot_time")
    
    # Если slot_time сбрасывается явно, сбрасываем и slot_time_verified
    if "slot_time" in extracted_data and extracted_data["slot_time"] is None:
        current_details["slot_time_verified"] = None
    
    # Если master_id сбрасывается явно, сбрасываем и master_name
    if "master_id" in extracted_data and extracted_data["master_id"] is None:
        current_details["master_id"] = None
        current_details.pop("master_name", None)  # Удаляем, если есть
    
    # Если master_name сбрасывается явно (независимо от master_id)
    if "master_name" in extracted_data and extracted_data["master_name"] is None:
        current_details.pop("master_name", None)  # Удаляем, если есть
    
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


def try_update_booking_state_from_reply(
    reply: str,
    current_booking_state: Dict[str, Any],
    extracted_info: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Пытается обновить состояние бронирования из JSON в ответе LLM
    
    Args:
        reply: Ответ от LLM (может содержать JSON)
        current_booking_state: Текущее состояние бронирования
        extracted_info: Текущий extracted_info из состояния
        
    Returns:
        Обновленный extracted_info или None, если JSON не найден
    """
    # Пытаемся распарсить JSON из ответа
    extracted_data = parse_json_from_response(reply)
    
    if not extracted_data:
        return None
    
    # Обновляем состояние бронирования
    updated_booking_state = merge_booking_state(current_booking_state, extracted_data)
    
    # Обновляем extracted_info
    updated_extracted_info = extracted_info.copy()
    updated_extracted_info["booking"] = updated_booking_state
    
    logger.info(f"Обнаружен JSON в ответе LLM, обновлено состояние бронирования: {extracted_data}")
    logger.info(f"Обновленное состояние бронирования: {updated_booking_state}")
    
    return updated_extracted_info


