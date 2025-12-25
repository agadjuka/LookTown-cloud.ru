"""
Инструмент для создания записи на услугу
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from ....common.thread import Thread

from ..common.yclients_service import YclientsService
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error
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
        description="Service ID. Get from FindService"
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
    
    @handle_technical_errors("создание записи")
    def process(self, thread: Thread) -> str:
        """
        Создание записи на услугу
        
        Returns:
            Сообщение о результате создания записи
        """
        try:
            yclients_service = YclientsService()
        except ValueError as e:
            return format_system_error(e, "создание записи")
        
        try:
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
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при создании записи: {e}", exc_info=True)
                return format_system_error(e, "создание записи")
            else:
                # Бизнес-ошибки должны обрабатываться в логике
                logger.error(f"Неожиданная ошибка при создании записи: {e}", exc_info=True)
                return format_system_error(e, "создание записи")

