"""
Логика для создания записи на услугу
Адаптировано из Cloud Function
"""
import asyncio
import json
from typing import Optional, Tuple, List
from ..common.yclients_service import YclientsService, Master
from ..common.phone_utils import normalize_phone
from ..common.book_times_logic import _normalize_name, _get_name_variants, _find_master_by_name
from ..common.error_handler import APIError


def _normalize_time(time_str: str) -> str:
    """
    Нормализует время, убирая ведущие нули
    '09:00' -> '9:00'
    '9:00' -> '9:00'
    
    Args:
        time_str: Время в формате HH:MM или H:MM
        
    Returns:
        str: Нормализованное время без ведущих нулей
    """
    if ':' not in time_str:
        return time_str
    
    parts = time_str.split(':')
    hour = int(parts[0])  # Убираем ведущие нули через конвертацию в int
    minute = parts[1]
    
    return f"{hour}:{minute}"


def _normalize_datetime_for_api(datetime_str: str) -> str:
    """
    Нормализует datetime к формату, ожидаемому API: YYYY-MM-DD HH:MM:SS
    Добавляет секунды, если их нет
    
    Args:
        datetime_str: Дата и время в формате YYYY-MM-DD HH:MM или YYYY-MM-DD HH:MM:SS
        
    Returns:
        str: Дата и время в формате YYYY-MM-DD HH:MM:SS
    """
    datetime_str = datetime_str.strip()
    
    # Поддерживаем форматы: "2025-11-08 14:30" или "2025-11-08T14:30" или "2025-11-08 14:30:00"
    if 'T' in datetime_str:
        parts = datetime_str.split('T', 1)
        date = parts[0]
        time = parts[1] if len(parts) > 1 else ""
    elif ' ' in datetime_str:
        parts = datetime_str.split(' ', 1)
        date = parts[0]
        time = parts[1] if len(parts) > 1 else ""
    else:
        # Если формат не распознан, возвращаем как есть
        return datetime_str
    
    # Обрабатываем время
    if time:
        # Убираем часовой пояс, если есть
        if '+' in time:
            time = time.split('+')[0]
        elif 'Z' in time:
            time = time.split('Z')[0]
        
        # Проверяем, есть ли секунды
        time_parts = time.split(':')
        if len(time_parts) == 2:
            # Нет секунд, добавляем :00
            return f"{date} {time}:00"
        elif len(time_parts) >= 3:
            # Есть секунды, возвращаем как есть (но убираем миллисекунды, если есть)
            seconds = time_parts[2].split('.')[0]  # Убираем миллисекунды
            return f"{date} {time_parts[0]}:{time_parts[1]}:{seconds}"
    
    # Если время не указано, возвращаем только дату с временем 00:00:00
    return f"{date} 00:00:00"


def _parse_datetime(datetime_str: str) -> Tuple[str, str]:
    """
    Разбирает строку datetime на дату и время
    
    Args:
        datetime_str: Строка с датой и временем
        
    Returns:
        Tuple[str, str]: (дата в формате YYYY-MM-DD, время в формате H:MM без ведущих нулей)
    """
    # Поддерживаем форматы: "2025-11-08 14:30" или "2025-11-08T14:30"
    datetime_str = datetime_str.strip()
    
    if 'T' in datetime_str:
        parts = datetime_str.split('T')
    elif ' ' in datetime_str:
        parts = datetime_str.split(' ')
    else:
        raise ValueError(f"Неверный формат datetime: {datetime_str}")
    
    date = parts[0]
    time = parts[1] if len(parts) > 1 else ""
    
    # Убираем секунды, если есть
    if ':' in time:
        time_parts = time.split(':')
        time = f"{time_parts[0]}:{time_parts[1]}"
    
    # Нормализуем время (убираем ведущие нули)
    time = _normalize_time(time)
    
    return date, time


async def _find_available_master(
    yclients_service: YclientsService,
    service_id: int,
    date: str,
    target_time: str,
    valid_masters: list
) -> Optional[Tuple[int, str]]:
    """
    Находит мастера, у которого есть свободный слот в указанное время
    
    Args:
        yclients_service: Сервис для работы с API
        service_id: ID услуги
        date: Дата в формате YYYY-MM-DD
        target_time: Целевое время в формате HH:MM
        valid_masters: Список валидных мастеров
        
    Returns:
        Optional[Tuple[int, str]]: (master_id, master_name) или None если не найдено
    """
    master_ids = [master.id for master in valid_masters]
    
    # Параллельно запрашиваем слоты для всех мастеров
    tasks = [
        yclients_service.get_book_times(
            master_id=master_id,
            date=date,
            service_id=service_id
        )
        for master_id in master_ids
    ]
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Нормализуем целевое время для корректного сравнения
    normalized_target_time = _normalize_time(target_time)
    
    # Проверяем каждого мастера на наличие нужного времени
    for master, response in zip(valid_masters, responses):
        if isinstance(response, Exception):
            continue
        
        # Нормализуем все времена из слотов для корректного сравнения
        available_times = [_normalize_time(slot.time) for slot in response.data]
        
        # Если найден слот с нужным временем, берем этого мастера
        if normalized_target_time in available_times:
            return (master.id, master.name)
    
    return None


async def create_booking_logic(
    yclients_service: YclientsService,
    service_id: int,
    client_name: str,
    client_phone: str,
    datetime: str,
    master_name: Optional[str] = None
) -> dict:
    """
    Основная логика создания записи на услугу
    
    Args:
        yclients_service: Сервис для работы с API
        service_id: ID услуги
        client_name: Имя клиента
        client_phone: Телефон клиента
        datetime: Дата и время записи в формате YYYY-MM-DD HH:MM или YYYY-MM-DDTHH:MM
        master_name: Имя мастера (опционально)
        
    Returns:
        dict: Результат создания записи с полями success, message, master_name, datetime, service_title, price (если доступна)
    """
    try:
        # 0. Нормализуем номер телефона к формату +7XXXXXXXXXX
        try:
            normalized_phone = normalize_phone(client_phone)
        except ValueError as e:
            return {
                "success": False,
                "message": f"Ошибка в номере телефона: {str(e)}"
            }
        
        # 1. Получаем детали услуги (мастера и продолжительность)
        service_details = await yclients_service.get_service_details(service_id)
        
        service_title = service_details.get_title()
        default_seance_length = service_details.duration  # Общая продолжительность услуги (fallback)
        
        # Проверяем, что это не "Лист ожидания"
        if service_title == "Лист ожидания":
            return {
                "success": False,
                "message": "Запись на 'Лист ожидания' невозможна"
            }
        
        # Фильтруем мастеров, исключая "Лист ожидания"
        all_masters = service_details.staff
        valid_masters = [
            master for master in all_masters
            if master.name != "Лист ожидания"
        ]
        
        # Если указан master_name, ищем конкретного мастера
        if master_name:
            found_master = _find_master_by_name(valid_masters, master_name)
            
            if not found_master:
                return {
                    "success": False,
                    "message": f"Мастер с именем '{master_name}' не найден для данной услуги",
                    "service_title": service_title
                }
            
            valid_masters = [found_master]
        
        if not valid_masters:
            return {
                "success": False,
                "message": "Нет доступных мастеров для данной услуги"
            }
        
        # 2. Разбираем дату и время
        date, target_time = _parse_datetime(datetime)
        
        # 3. Находим мастера с доступным слотом
        master_info = await _find_available_master(
            yclients_service=yclients_service,
            service_id=service_id,
            date=date,
            target_time=target_time,
            valid_masters=valid_masters
        )
        
        if not master_info:
            return {
                "success": False,
                "message": f"К сожалению, на {datetime} нет свободных мастеров для услуги '{service_title}'",
                "service_title": service_title,
                "datetime": datetime
            }
        
        master_id, master_name_result = master_info
        
        # 4. Находим выбранного мастера в списке и берем его seance_length
        selected_master = None
        for master in all_masters:
            if master.id == master_id:
                selected_master = master
                break
        
        # Берем seance_length из конкретного мастера, если есть, иначе используем общую продолжительность
        if selected_master and selected_master.seance_length is not None:
            seance_length = selected_master.seance_length
        else:
            seance_length = default_seance_length
        
        # 5. Нормализуем datetime для API (добавляем секунды, если их нет)
        normalized_datetime = _normalize_datetime_for_api(datetime)
        
        # 6. Создаем запись
        booking_response = await yclients_service.create_booking(
            staff_id=master_id,
            service_id=service_id,
            client_name=client_name,
            client_phone=normalized_phone,  # Используем нормализованный номер
            datetime=normalized_datetime,
            seance_length=seance_length
        )
        
        if not booking_response.get("success"):
            # Пытаемся извлечь структурированную информацию об ошибке
            error_data = booking_response.get("error_data")
            error_msg = booking_response.get("error", "Неизвестная ошибка")
            status_code = booking_response.get("status_code")
            
            # Если есть статус код от API (4xx/5xx) - это техническая ошибка API
            if status_code:
                # Извлекаем сообщение из meta, если есть
                error_message = error_msg
                if error_data and isinstance(error_data, dict):
                    meta = error_data.get("meta", {})
                    if isinstance(meta, dict):
                        meta_message = meta.get("message", "")
                        if meta_message:
                            error_message = meta_message
                
                # Выбрасываем исключение, которое будет обработано как техническая ошибка
                raise APIError(status_code=status_code, message=error_message)
            
            # Если нет status_code, но есть ошибка - это бизнес-логика
            if error_data and isinstance(error_data, dict):
                meta = error_data.get("meta", {})
                if isinstance(meta, dict):
                    meta_message = meta.get("message", "")
                    if meta_message:
                        error_msg = meta_message
            
            return {
                "success": False,
                "message": f"Ошибка при создании записи: {error_msg}",
                "service_title": service_title
            }
        
        # 6. Извлекаем цену и другие данные из ответа API
        price = None
        response_data = booking_response.get("data", {})
        
        # Структура ответа: data.data.services[0].cost
        if isinstance(response_data, dict):
            # Проверяем вложенную структуру data.data
            nested_data = response_data.get("data", {})
            if isinstance(nested_data, dict):
                # Ищем цену в services[0].cost
                services = nested_data.get("services", [])
                if services and isinstance(services, list) and len(services) > 0:
                    first_service = services[0]
                    if isinstance(first_service, dict):
                        price = first_service.get("cost") or first_service.get("price")
        
        # 8. Форматируем дату и время в удобный формат
        def format_datetime_russian(datetime_str: str) -> str:
            """Форматирует дату и время в русский формат: '13 ноября 2025, 12:00'"""
            try:
                from datetime import datetime
                
                # Парсим дату и время
                date_part = ""
                time_part = ""
                
                if 'T' in datetime_str:
                    parts = datetime_str.split('T', 1)
                    date_part = parts[0]
                    if len(parts) > 1:
                        # Убираем часовой пояс и секунды
                        time_str = parts[1]
                        if '+' in time_str:
                            time_str = time_str.split('+')[0]
                        elif '-' in time_str and len(time_str.split('-')) > 3:
                            # Проверяем, не является ли последняя часть часовым поясом
                            time_parts = time_str.rsplit('-', 1)
                            if ':' in time_parts[-1]:
                                time_str = time_parts[0]
                        time_parts = time_str.split(':')
                        if len(time_parts) >= 2:
                            time_part = f"{time_parts[0]}:{time_parts[1]}"
                elif ' ' in datetime_str:
                    parts = datetime_str.split(' ', 1)
                    date_part = parts[0]
                    if len(parts) > 1:
                        time_str = parts[1]
                        # Убираем секунды, если есть
                        time_parts = time_str.split(':')
                        if len(time_parts) >= 2:
                            time_part = f"{time_parts[0]}:{time_parts[1]}"
                else:
                    date_part = datetime_str
                
                # Парсим дату
                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                
                # Названия месяцев в родительном падеже
                months_ru = {
                    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                    5: "мая", 6: "июня", 7: "июля", 8: "августа",
                    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                }
                
                day = date_obj.day
                month = months_ru[date_obj.month]
                year = date_obj.year
                
                # Форматируем дату: "13 ноября 2025"
                date_formatted = f"{day} {month} {year}"
                
                # Форматируем время (убираем ведущие нули)
                if time_part:
                    time_parts = time_part.split(':')
                    if len(time_parts) >= 2:
                        hours = str(int(time_parts[0]))  # Убираем ведущие нули
                        minutes = time_parts[1]
                        time_formatted = f"{hours}:{minutes}"
                        return f"{date_formatted}, {time_formatted}"
                
                return date_formatted
            except Exception as e:
                # В случае ошибки возвращаем исходную строку
                return datetime_str
        
        formatted_datetime = format_datetime_russian(datetime)
        
        # 7. Формируем успешный ответ с полной информацией
        message_lines = [
            f"{client_name}, Вы записаны на услугу:",
            f"**{service_title}**",
            f"",
            f"**Дата и время:** {formatted_datetime}",
            f"**Мастер:** {master_name_result}"
        ]
        
        if price is not None:
            message_lines.append(f"**Цена:** {price} руб.")
        
        message_lines.append("")
        message_lines.append("Будем вас ждать! 🌻")
        message_lines.append("\n((Отправь клиенту именно этот текст с сохранением форматирования и **))")
        
        message = "\n".join(message_lines)
        
        result = {
            "success": True,
            "message": message,
            "master_name": master_name_result,
            "datetime": datetime,
            "service_title": service_title,
            "client_name": client_name
        }
        
        # Добавляем цену, если она была найдена
        if price is not None:
            result["price"] = price
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка при обработке запроса: {str(e)}"
        }
