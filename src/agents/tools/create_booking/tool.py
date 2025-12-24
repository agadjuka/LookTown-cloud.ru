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
    Create a booking for a service.
    Use when the client has chosen a service, date, time and provided their data (name and phone).
    """
    
    service_id: int = Field(
        description="Service ID. Get from GetServices"
    )
    
    client_name: str = Field(
        description="Client name"
    )
    
    client_phone: str = Field(
        description="Client phone"
    )
    
    datetime: str = Field(
        description="Booking date and time in format YYYY-MM-DD HH:MM"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Master name (optional) (if the client explicitly asked to book with a specific master). DO NOT specify if the client did not ask for a specific master."
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

