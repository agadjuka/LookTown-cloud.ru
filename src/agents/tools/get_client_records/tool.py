"""
Инструмент для получения записей клиента по номеру телефона
"""
import asyncio
from datetime import datetime
import pytz
from pydantic import BaseModel, Field
from ....common.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import get_client_records_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()

# Названия месяцев в родительном падеже для форматирования даты
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def _format_datetime_russian(datetime_str: str) -> str:
    """
    Форматирует дату и время в русский формат: "12 ноября 2025, 14:30"
    Убирает часовой пояс из времени
    
    Args:
        datetime_str: Строка с датой и временем (например: "2025-11-12T14:30:00+03:00" или "2025-11-12 14:30")
        
    Returns:
        Отформатированная строка: "12 ноября 2025, 14:30"
    """
    if not datetime_str:
        return "Не указано"
    
    try:
        # Убираем часовой пояс, если он есть
        datetime_str_clean = datetime_str.split('+')[0] if '+' in datetime_str else datetime_str
        datetime_str_clean = datetime_str_clean.split('Z')[0] if 'Z' in datetime_str_clean else datetime_str_clean
        # Убираем часовой пояс в формате -03:00
        if '-' in datetime_str_clean and len(datetime_str_clean.split('-')) > 3:
            # Если есть более 3 частей после разбиения по '-', значит есть часовой пояс
            parts = datetime_str_clean.rsplit('-', 1)
            if ':' in parts[-1] and len(parts[-1].split(':')) == 2:
                # Последняя часть похожа на часовой пояс (например, "03:00")
                datetime_str_clean = parts[0]
        
        # Парсим дату и время
        # Поддерживаем форматы: "2025-11-12T14:30:00", "2025-11-12 14:30", "2025-11-12T14:30"
        if 'T' in datetime_str_clean:
            date_part, time_part = datetime_str_clean.split('T', 1)
        elif ' ' in datetime_str_clean:
            date_part, time_part = datetime_str_clean.split(' ', 1)
        else:
            date_part = datetime_str_clean
            time_part = ""
        
        # Парсим дату
        date_obj = datetime.strptime(date_part, "%Y-%m-%d")
        day = date_obj.day
        month = date_obj.month
        year = date_obj.year
        
        # Форматируем дату: "12 ноября 2025"
        date_formatted = f"{day} {MONTHS_RU[month]} {year}"
        
        # Форматируем время (убираем секунды и часовой пояс)
        if time_part:
            # Убираем секунды, если есть
            time_parts = time_part.split(':')
            if len(time_parts) >= 2:
                hours = time_parts[0].lstrip('0') or '0'
                minutes = time_parts[1]
                time_formatted = f"{hours}:{minutes}"
                return f"{date_formatted}, {time_formatted}"
        
        return date_formatted
        
    except Exception as e:
        logger.error(f"Ошибка при форматировании даты {datetime_str}: {e}")
        return datetime_str


def _is_future_record(datetime_str: str) -> bool:
    """
    Проверяет, является ли запись будущей (дата и время еще не прошли)
    Использует московское время для сравнения, так как записи приходят в московском часовом поясе
    
    Args:
        datetime_str: Строка с датой и временем (например: "2025-11-12T14:30:00+03:00")
        
    Returns:
        True если запись в будущем, False если в прошлом
    """
    if not datetime_str:
        return False
    
    try:
        # Получаем московский часовой пояс
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Пытаемся распарсить datetime с учетом часового пояса
        record_datetime = None
        
        # Пробуем распарсить с часовым поясом
        try:
            # Если есть часовой пояс в строке, используем fromisoformat
            if '+' in datetime_str or datetime_str.endswith('Z'):
                if datetime_str.endswith('Z'):
                    datetime_str = datetime_str[:-1] + '+00:00'
                record_datetime_parsed = datetime.fromisoformat(datetime_str)
                # Если datetime уже имеет timezone info, конвертируем в московское время для сравнения
                if record_datetime_parsed.tzinfo is not None:
                    # Конвертируем в московское время
                    record_datetime = record_datetime_parsed.astimezone(moscow_tz)
                else:
                    # Если timezone info нет, локализуем как московское время
                    record_datetime = moscow_tz.localize(record_datetime_parsed)
            else:
                # Если часового пояса нет, предполагаем московское время
                # Убираем возможные артефакты
                datetime_str_clean = datetime_str.split('+')[0] if '+' in datetime_str else datetime_str
                datetime_str_clean = datetime_str_clean.split('Z')[0] if 'Z' in datetime_str_clean else datetime_str_clean
                
                # Парсим дату и время
                if 'T' in datetime_str_clean:
                    date_part, time_part = datetime_str_clean.split('T', 1)
                elif ' ' in datetime_str_clean:
                    date_part, time_part = datetime_str_clean.split(' ', 1)
                else:
                    date_part = datetime_str_clean
                    time_part = "00:00:00"
                
                # Формируем строку для парсинга
                if time_part:
                    # Убираем секунды из времени
                    time_parts = time_part.split(':')
                    time_clean = f"{time_parts[0]}:{time_parts[1]}" if len(time_parts) >= 2 else "00:00"
                    parse_str = f"{date_part} {time_clean}"
                else:
                    parse_str = f"{date_part} 00:00"
                
                # Парсим datetime без часового пояса
                try:
                    record_datetime_naive = datetime.strptime(parse_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    # Пробуем без времени
                    record_datetime_naive = datetime.strptime(date_part, "%Y-%m-%d")
                
                # Локализуем в московский часовой пояс
                record_datetime = moscow_tz.localize(record_datetime_naive)
        except (ValueError, AttributeError) as e:
            logger.error(f"Ошибка при парсинге даты {datetime_str}: {e}")
            return False
        
        if record_datetime is None:
            return False
        
        # Получаем текущее московское время
        current_datetime = datetime.now(moscow_tz)
        
        # Сравниваем с текущим временем
        return record_datetime > current_datetime
        
    except Exception as e:
        logger.error(f"Ошибка при проверке даты {datetime_str}: {e}")
        return False


class GetClientRecords(BaseModel):
    """
    Find a client by phone number and get all their future bookings.
    """
    
    phone: str = Field(
        description="Client phone number"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск клиента по телефону и получение всех его записей
        
        Returns:
            Отформатированная информация о клиенте и его записях
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            result = asyncio.run(
                get_client_records_logic(
                    yclients_service=yclients_service,
                    phone=self.phone
                )
            )
            
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
            client = result.get('client', {})
            records = result.get('records', [])
            
            # Фильтруем только будущие записи
            future_records = [
                record for record in records 
                if _is_future_record(record.get('datetime', ''))
            ]
            
            # Форматируем информацию о клиенте
            client_name = client.get('name', 'Не указано')
            client_id = client.get('id')
            client_phone = client.get('phone', self.phone)
            
            # Форматируем имя клиента с ID в скобках
            if client_id:
                client_info = f"{client_name} (ID: {client_id})"
            else:
                client_info = client_name
            
            result_text = f"Клиент: {client_info}\nТелефон: {client_phone}\n\n"
            
            # Форматируем записи
            if not future_records:
                result_text += "У клиента нет будущих записей."
            else:
                result_text += f"Найдено будущих записей: {len(future_records)}\n\n"
                
                for idx, record in enumerate(future_records, 1):
                    record_info = f"{idx}. "
                    
                    # Дата и время в русском формате
                    datetime_str = record.get('datetime', '')
                    if datetime_str:
                        formatted_datetime = _format_datetime_russian(datetime_str)
                        record_info += f"Дата и время: {formatted_datetime}\n   "
                    
                    # Услуга
                    service_title = record.get('service_title')
                    if service_title:
                        record_info += f"Услуга: {service_title}"
                        service_id = record.get('service_id')
                        if service_id:
                            record_info += f" (ID: {service_id})"
                        record_info += "\n   "
                    
                    # Мастер
                    staff_name = record.get('staff_name')
                    if staff_name:
                        record_info += f"Мастер: {staff_name}"
                        staff_id = record.get('staff_id')
                        if staff_id:
                            record_info += f" (ID: {staff_id})"
                        record_info += "\n   "
                    
                    # Продолжительность сеанса
                    seance_length = record.get('seance_length')
                    if seance_length:
                        record_info += f"Продолжительность: {seance_length} сек.\n   "
                    
                    # ID записи
                    record_id = record.get('record_id')
                    if record_id:
                        record_info += f"ID записи: {record_id}\n   "
                    
                    # ID клиента
                    if client_id:
                        record_info += f"ID клиента: {client_id}"
                    
                    result_text += record_info + "\n"
            
            return result_text
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации GetClientRecords: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при получении записей клиента: {e}", exc_info=True)
            return f"Ошибка при получении записей клиента: {str(e)}"

