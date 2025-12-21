"""
Логика для поиска доступных слотов по периодам времени
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from ..common.yclients_service import YclientsService, Master
from ..common.book_times_logic import _find_master_by_name, _merge_consecutive_slots


def _parse_time_string(time_str: str) -> int:
    """
    Парсит строку времени в формате HH:MM или HH.MM в минуты от начала дня.
    
    Args:
        time_str: Время в формате "16:00" или "16.00"
        
    Returns:
        Минуты от начала дня
    """
    # Поддерживаем оба формата: "16:00" и "16.00"
    time_str = time_str.replace('.', ':')
    parts = time_str.split(':')
    if len(parts) < 2:
        raise ValueError(f"Неверный формат времени: {time_str}. Ожидается HH:MM или HH.MM")
    
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    
    if hours < 0 or hours >= 24 or minutes < 0 or minutes >= 60:
        raise ValueError(f"Неверное время: {time_str}")
    
    return hours * 60 + minutes


def _get_time_period_bounds(time_period: str) -> tuple[int, int]:
    """
    Возвращает границы времени для периода в минутах от начала дня.
    
    Поддерживаемые форматы:
    - "morning", "day", "evening" - предопределенные периоды
    - "16:00" или "16.00" - конкретное время (слот 30 минут)
    - "16:00-19:00" или "16.00-19.00" - интервал времени
    - "before 11:00" или "before 11.00" - до указанного времени
    - "after 16:00" или "after 16.00" - после указанного времени
    
    Args:
        time_period: Период времени в любом из поддерживаемых форматов
        
    Returns:
        Tuple (start_minutes, end_minutes)
    """
    time_period = time_period.strip().lower()
    
    # Предопределенные периоды
    periods = {
        "morning": (9 * 60, 11 * 60),  # 9:00 - 11:00
        "day": (11 * 60, 17 * 60),     # 11:00 - 17:00
        "evening": (17 * 60, 22 * 60)  # 17:00 - 22:00
    }
    
    if time_period in periods:
        return periods[time_period]
    
    # "before HH:MM" или "before HH.MM"
    if time_period.startswith("before "):
        time_str = time_period[7:].strip()
        end_minutes = _parse_time_string(time_str)
        return (0, end_minutes)
    
    # "after HH:MM" или "after HH.MM"
    if time_period.startswith("after "):
        time_str = time_period[6:].strip()
        start_minutes = _parse_time_string(time_str)
        return (start_minutes, 24 * 60)
    
    # Интервал "HH:MM-HH:MM" или "HH.MM-HH.MM"
    if '-' in time_period:
        parts = time_period.split('-', 1)
        if len(parts) == 2:
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            start_minutes = _parse_time_string(start_str)
            end_minutes = _parse_time_string(end_str)
            return (start_minutes, end_minutes)
    
    # Конкретное время "HH:MM" или "HH.MM" (слот 30 минут)
    try:
        time_minutes = _parse_time_string(time_period)
        return (time_minutes, time_minutes + 30)
    except ValueError:
        return (0, 24 * 60)


def _time_to_minutes(time_str: str) -> int:
    """Преобразует время в формате HH:MM в минуты от начала дня."""
    parts = time_str.split(':')
    return int(parts[0]) * 60 + int(parts[1])


def _filter_times_by_period(times: List[str], time_period: str) -> List[str]:
    """
    Фильтрует отдельные временные точки по периоду времени.
    
    Args:
        times: Список временных точек в формате "HH:MM"
        time_period: Период времени в любом из поддерживаемых форматов
        
    Returns:
        Отфильтрованный список временных точек
    """
    start_bound, end_bound = _get_time_period_bounds(time_period)
    filtered = []
    
    for time_str in times:
        time_minutes = _time_to_minutes(time_str)
        if start_bound <= time_minutes <= end_bound:
            filtered.append(time_str)
    
    return filtered


def _parse_date_range(date_range: str) -> tuple[str, str]:
    """
    Парсит интервал дат в формате "YYYY-MM-DD:YYYY-MM-DD".
    
    Args:
        date_range: Интервал дат в формате "YYYY-MM-DD:YYYY-MM-DD"
        
    Returns:
        Tuple (start_date, end_date)
    """
    parts = date_range.split(':')
    if len(parts) != 2:
        raise ValueError(f"Неверный формат интервала дат: {date_range}. Ожидается формат YYYY-MM-DD:YYYY-MM-DD")
    
    start_date = parts[0].strip()
    end_date = parts[1].strip()
    
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Неверный формат даты: {e}")
    
    return start_date, end_date


def _generate_date_list(start_date: str, end_date: str) -> List[str]:
    """
    Генерирует список дат от start_date до end_date включительно.
    
    Args:
        start_date: Начальная дата в формате YYYY-MM-DD
        end_date: Конечная дата в формате YYYY-MM-DD
        
    Returns:
        Список дат в формате YYYY-MM-DD
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    return dates


async def find_slots_by_period(
    yclients_service: YclientsService,
    service_id: int,
    time_period: str,
    master_name: Optional[str] = None,
    master_id: Optional[int] = None,
    date: Optional[str] = None,
    date_range: Optional[str] = None
) -> Dict[str, any]:
    """
    Находит доступные слоты для услуги с фильтрацией по периоду времени.
    Если time_period пустой или None, находит ближайшие доступные слоты без фильтрации по времени.
    
    Args:
        yclients_service: Экземпляр сервиса Yclients
        service_id: ID услуги
        time_period: Период времени ("morning", "day", "evening") или пустая строка для поиска всех слотов
        master_name: Имя мастера (опционально)
        master_id: ID мастера (опционально)
        date: Конкретная дата в формате "YYYY-MM-DD" (опционально). Если указана, date_range игнорируется.
        date_range: Интервал дат в формате "YYYY-MM-DD:YYYY-MM-DD" (опционально). Используется только если date не указан.
        
    Returns:
        Dict с результатами поиска:
        - service_title: Название услуги
        - master_name: Имя мастера (если указан)
        - results: Список результатов по датам
        - error: Сообщение об ошибке (если есть)
    """
    filter_by_time = bool(time_period and time_period.strip())
    
    if filter_by_time:
        try:
            _get_time_period_bounds(time_period)
        except Exception as e:
            return {
                "error": f"Неверный формат периода времени: {time_period}. Поддерживаемые форматы: 'morning', 'day', 'evening', '16:00', '16:00-19:00', 'before 11:00', 'after 16:00'. Ошибка: {str(e)}"
            }
    
    try:
        service_details = await yclients_service.get_service_details(service_id)
    except Exception as e:
        return {
            "error": f"Ошибка при получении информации об услуге: {str(e)}"
        }
    
    service_name = service_details.name or service_details.title
    if service_name == "Лист ожидания":
        return {
            "service_title": service_name,
            "masters": []
        }
    
    service_title = service_details.get_title()
    
    all_masters = service_details.staff
    valid_masters = [
        master for master in all_masters 
        if master.name != "Лист ожидания"
    ]
    
    master_ids = []
    result_master_name = None
    
    if master_id:
        master_ids = [master_id]
        for master in valid_masters:
            if master.id == master_id:
                result_master_name = master.name
                break
        if not result_master_name:
            try:
                staff_list = await yclients_service.get_staff_list()
                for staff in staff_list:
                    if staff.get('id') == master_id:
                        result_master_name = staff.get('name')
                        break
            except Exception:
                pass
    elif master_name:
        found_master = _find_master_by_name(valid_masters, master_name)
        if not found_master:
            return {
                "service_title": service_title,
                "masters": [],
                "error": f"Мастер с именем '{master_name}' не найден для данной услуги"
            }
        master_ids = [found_master.id]
        result_master_name = found_master.name
    else:
        master_ids = [master.id for master in valid_masters]
    
    if not master_ids:
        return {
            "service_title": service_title,
            "masters": [],
            "error": "Не найдено мастеров для данной услуги"
        }
    
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
            dates_to_check = [date]
        except ValueError as e:
            return {
                "error": f"Неверный формат даты: {date}. Ожидается формат YYYY-MM-DD. Ошибка: {str(e)}"
            }
    elif date_range:
        try:
            start_date, end_date = _parse_date_range(date_range)
            dates_to_check = _generate_date_list(start_date, end_date)
        except ValueError as e:
            return {
                "error": str(e)
            }
    else:
        today = datetime.now().date()
        dates_to_check = []
        max_checks = 10
        
        for i in range(max_checks):
            check_date = today + timedelta(days=i)
            dates_to_check.append(check_date.strftime("%Y-%m-%d"))
    
    tasks = []
    for check_date in dates_to_check:
        for master_id in master_ids:
            tasks.append(
                yclients_service.get_book_times(
                    master_id=master_id,
                    date=check_date,
                    service_id=service_id
                )
            )
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Храним слоты по мастерам: master_slots[master_id][date] = set()
    master_slots = {}
    for master_id in master_ids:
        master_slots[master_id] = {}
        for check_date in dates_to_check:
            master_slots[master_id][check_date] = set()
    
    task_index = 0
    for check_date in dates_to_check:
        for master_id in master_ids:
            response = responses[task_index]
            task_index += 1
            
            if isinstance(response, Exception):
                continue
            
            for slot in response.data:
                master_slots[master_id][check_date].add(slot.time)
    
    # Создаем словарь для имен мастеров
    master_names_dict = {}
    for master in valid_masters:
        if master.id in master_ids:
            master_names_dict[master.id] = master.name
    
    if result_master_name and len(master_ids) == 1:
        # Если указан конкретный мастер, используем его имя
        master_names_dict[master_ids[0]] = result_master_name
    
    target_days = 3 if not date and not date_range else len(dates_to_check)
    
    if filter_by_time:
        start_bound, end_bound = _get_time_period_bounds(time_period)
    
    # Обрабатываем каждого мастера отдельно
    masters_results = []
    for master_id in master_ids:
        master_name = master_names_dict.get(master_id, f"Мастер {master_id}")
        master_results = []
        days_found = 0
        
        for check_date in dates_to_check:
            if not date and not date_range and days_found >= target_days:
                break
            
            times = sorted(list(master_slots[master_id][check_date]), key=_time_to_minutes)
            
            if not times:
                continue
            
            if filter_by_time:
                filtered_times = _filter_times_by_period(times, time_period)
                
                if not filtered_times:
                    continue
                
                intervals = _merge_consecutive_slots(filtered_times)
                
                final_intervals = []
                for interval in intervals:
                    start_time_str = interval.split('-')[0].strip()
                    start_minutes = _time_to_minutes(start_time_str)
                    
                    if start_bound <= start_minutes <= end_bound:
                        final_intervals.append(interval)
            else:
                intervals = _merge_consecutive_slots(times)
                final_intervals = intervals
            
            if final_intervals:
                master_results.append({
                    "date": check_date,
                    "slots": final_intervals
                })
                days_found += 1
        
        if master_results:
            masters_results.append({
                "master_id": master_id,
                "master_name": master_name,
                "results": master_results
            })
    
    result = {
        "service_title": service_title,
        "time_period": time_period if filter_by_time else "",
        "masters": masters_results
    }
    
    return result

