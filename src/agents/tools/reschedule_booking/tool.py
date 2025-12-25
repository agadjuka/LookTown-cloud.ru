"""
Инструмент для переноса записи клиента
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from ....common.thread import Thread

from ..common.yclients_service import YclientsService
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error
from .logic import reschedule_booking_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class RescheduleBooking(BaseModel):
    """
    Reschedule a client's booking to a new time.
    Use when the client asks to reschedule a booking to another time or date.
    """
    
    record_id: int = Field(
        description="Booking ID. Get from GetClientRecords"
    )
    
    datetime: str = Field(
        description="New date and time in format YYYY-MM-DD HH:MM"
    )
    
    staff_id: int = Field(
        description="Master ID. Get from GetClientRecords"
    )
    
    service_id: int = Field(
        description="Service ID. Get from GetClientRecords"
    )
    
    client_id: int = Field(
        description="Client ID. Get from GetClientRecords"
    )
    
    seance_length: int = Field(
        description="Session duration in seconds. Get from GetClientRecords"
    )
    
    save_if_busy: Optional[bool] = Field(
        default=False,
        description="Save booking even if slot is busy (default False). Usually don't use."
    )
    
    @handle_technical_errors("перенос записи")
    def process(self, thread: Thread) -> str:
        """
        Перенос записи на новое время
        
        Returns:
            Сообщение о результате переноса записи
        """
        try:
            yclients_service = YclientsService()
        except ValueError as e:
            return format_system_error(e, "перенос записи")
        
        try:
            result = asyncio.run(
                reschedule_booking_logic(
                    yclients_service=yclients_service,
                    record_id=self.record_id,
                    datetime=self.datetime,
                    staff_id=self.staff_id,
                    service_id=self.service_id,
                    client_id=self.client_id,
                    seance_length=self.seance_length,
                    save_if_busy=self.save_if_busy
                )
            )
            
            if result.get('success'):
                return result.get('message', 'Запись успешно перенесена')
            else:
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при переносе записи: {e}", exc_info=True)
                return format_system_error(e, "перенос записи")
            else:
                logger.error(f"Неожиданная ошибка при переносе записи: {e}", exc_info=True)
                return format_system_error(e, "перенос записи")

