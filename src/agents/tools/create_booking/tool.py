"""
Инструмент для создания записи на услугу
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import create_booking_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class CreateBooking(BaseModel):
    """
    Создать запись на услугу.
    Используй когда клиент выбрал услугу, дату, время и предоставил свои данные (имя и телефон).
    """
    
    service_id: int = Field(
        description="ID услуги. Получи из GetServices"
    )
    
    client_name: str = Field(
        description="Имя клиента"
    )
    
    client_phone: str = Field(
        description="Телефон клиента"
    )
    
    datetime: str = Field(
        description="Дата и время записи в формате YYYY-MM-DD HH:MM"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (опционально) (если клиент явно просил записаться к конкретному мастеру). НЕ УКАЗЫВАЙ если клиент не просил конкретного мастера."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Создание записи на услугу
        
        Returns:
            Сообщение о результате создания записи
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            result = asyncio.run(
                create_booking_logic(
                    yclients_service=yclients_service,
                    service_id=self.service_id,
                    client_name=self.client_name,
                    client_phone=self.client_phone,
                    datetime=self.datetime,
                    master_name=self.master_name
                )
            )
            
            return result.get('message', 'Неизвестная ошибка')
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации CreateBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при создании записи: {e}", exc_info=True)
            return f"Ошибка при создании записи: {str(e)}"

