"""
Инструмент для отмены записи клиента
"""
import asyncio
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
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
    
    def process(self, thread: Thread) -> str:
        """
        Отмена записи по ID
        
        Returns:
            Сообщение о результате отмены записи
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
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
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации CancelBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при отмене записи: {e}", exc_info=True)
            return f"Ошибка при отмене записи: {str(e)}"

