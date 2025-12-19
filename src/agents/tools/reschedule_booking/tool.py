"""
Инструмент для переноса записи клиента
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
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
    Перенести запись клиента на новое время.
    Используй когда клиент просит перенести запись на другое время или дату.
    """
    
    record_id: int = Field(
        description="ID записи. Получи из GetClientRecords"
    )
    
    datetime: str = Field(
        description="Новое дата и время в формате YYYY-MM-DD HH:MM"
    )
    
    staff_id: int = Field(
        description="ID мастера. Получи из GetClientRecords"
    )
    
    service_id: int = Field(
        description="ID услуги. Получи из GetClientRecords"
    )
    
    client_id: int = Field(
        description="ID клиента.  Получи из GetClientRecords"
    )
    
    seance_length: int = Field(
        description="Продолжительность сеанса в секундах. Получи из GetClientRecords"
    )
    
    save_if_busy: Optional[bool] = Field(
        default=False,
        description="Сохранить запись даже если слот занят (по умолчанию False). Обычно не используй."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Перенос записи на новое время
        
        Returns:
            Сообщение о результате переноса записи
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
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
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации RescheduleBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при переносе записи: {e}", exc_info=True)
            return f"Ошибка при переносе записи: {str(e)}"

