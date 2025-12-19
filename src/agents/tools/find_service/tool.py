"""
Инструмент для поиска услуг по названию
"""
import asyncio
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import find_service_logic

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
    """
    
    service_name: str = Field(
        description="Название услуги для поиска (текст)"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск услуг по названию
        
        Returns:
            Отформатированная информация о найденных услугах (название, ID, цена)
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
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
            if len(services) == 1:
                result_lines.append("Найдена услуга:")
            else:
                result_lines.append(f"Найдено услуг: {len(services)}")
            
            result_lines.append("")
            
            for idx, service in enumerate(services, start=1):
                title = service.get('title', 'Неизвестно')
                service_id = service.get('id', 'Не указан')
                price = service.get('price', 'Не указана')
                
                result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске услуг: {e}", exc_info=True)
            return f"Ошибка при поиске услуг: {str(e)}"

