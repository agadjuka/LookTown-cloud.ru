"""
Инструмент для отмены записи клиента
"""
import asyncio
from pydantic import BaseModel, Field
from ....common.thread import Thread

from ..common.yclients_service import YclientsService
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error
from .logic import cancel_booking_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class CancelBooking(BaseModel):
    """
    Cancel a client's booking by booking ID.
    """
    
    record_id: int = Field(
        description="Booking ID. Get from GetClientRecords"
    )
    
    @handle_technical_errors("отмена записи")
    def process(self, thread: Thread) -> str:
        """
        Отмена записи по ID
        
        Returns:
            Сообщение о результате отмены записи
        """
        try:
            yclients_service = YclientsService()
        except ValueError as e:
            return format_system_error(e, "отмена записи")
        
        try:
            result = asyncio.run(
                cancel_booking_logic(
                    yclients_service=yclients_service,
                    record_id=self.record_id
                )
            )
            
            if result.get('success'):
                return result.get('message', 'Запись успешно отменена')
            else:
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при отмене записи: {e}", exc_info=True)
                return format_system_error(e, "отмена записи")
            else:
                logger.error(f"Неожиданная ошибка при отмене записи: {e}", exc_info=True)
                return format_system_error(e, "отмена записи")

