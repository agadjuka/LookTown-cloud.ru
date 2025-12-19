"""
Инструмент для поиска мастера по имени и услуге
"""
import asyncio
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import find_master_by_service_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class FindMasterByService(BaseModel):
    """
    Найти мастера по имени и услуге.
    """
    
    master_name: str = Field(
        description="Имя мастера"
    )
    
    service_name: str = Field(
        description="Название услуги"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск мастера по имени и услуге
        
        Returns:
            Отформатированная информация о мастере и его услугах
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
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
            
            services_text = "\n".join([
                f"  • {service['title']} (ID: {service['id']})"
                for service in services
            ])
            
            result_text = (
                f"Найден мастер: {master_name_result}"
            )
            
            if position_title:
                result_text += f" ({position_title})"
            
            result_text += f"\nID мастера: {master_id}\n\n"
            result_text += f"Доступные услуги:\n{services_text}"
            
            return result_text
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindMasterByService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске мастера: {e}", exc_info=True)
            return f"Ошибка при поиске мастера: {str(e)}"

