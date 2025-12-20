"""
Инструмент для поиска услуг по названию
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import find_service_logic, find_master_by_service_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class FindService(BaseModel):
    """
    Найти услуги по названию. Поиск выполняется по похожим названиям, не требует точного совпадения.
    Если указано имя мастера, то ищет мастера по имени и услуге, возвращая информацию о мастере и его услугах.
    """
    
    service_name: str = Field(
        description="Название услуги для поиска (текст)"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (необязательное поле). Если указано, то ищет мастера по имени и услуге"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск услуг по названию или мастера по имени и услуге
        
        Returns:
            Отформатированная информация о найденных услугах или мастере и его услугах
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Если указано имя мастера, используем логику поиска мастера по услуге
            if self.master_name:
                result = asyncio.run(
                    find_master_by_service_logic(
                        yclients_service=yclients_service,
                        master_name=self.master_name,
                        service_name=self.service_name
                    )
                )
                
                if not result.get('success'):
                    error = result.get('error', 'Неизвестная ошибка')
                    return f"Ошибка: {error}"
                
                master = result.get('master', {})
                master_name_result = master.get('name', '')
                master_id = master.get('id', '')
                position_title = master.get('position_title', '')
                
                services = result.get('services', [])
                
                if not services:
                    return f"Мастер {master_name_result} найден, но у него нет доступных услуг."
                
                # Форматируем результат как нумерованный список (топ-10 самых релевантных)
                result_lines = []
                
                for idx, service in enumerate(services, start=1):
                    title = service.get('title', 'Неизвестно')
                    service_id = service.get('id', 'Не указан')
                    price = service.get('price', 'Не указана')
                    
                    result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
                
                # Добавляем инструкцию в конце
                result_lines.append("")
                result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
                
                return "\n".join(result_lines)
            
            # Обычный поиск услуг
            result = asyncio.run(
                find_service_logic(
                    yclients_service=yclients_service,
                    service_name=self.service_name
                )
            )
            
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
            services = result.get('services', [])
            
            if not services:
                return f"Услуги с названием '{self.service_name}' не найдены"
            
            # Форматируем результат
            result_lines = []
            
            for idx, service in enumerate(services, start=1):
                title = service.get('title', 'Неизвестно')
                service_id = service.get('id', 'Не указан')
                price = service.get('price', 'Не указана')
                
                result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
            
            # Добавляем инструкцию в конце
            result_lines.append("")
            result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске услуг: {e}", exc_info=True)
            return f"Ошибка при поиске услуг: {str(e)}"

