"""
Инструмент для получения информации о мастерах
"""
from pydantic import BaseModel
from ....common.thread import Thread

from ..common.masters_data_loader import _masters_data_loader
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error
from .formatter import MastersFormatter

try:
    from ....services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class Masters(BaseModel):
    """
    Get complete information about salon masters.
    Use when the client asks "какие у вас мастера?", "расскажите про мастеров", "кто работает в салоне" or similar questions about masters.
    """
    
    @handle_technical_errors("получение информации о мастерах")
    def process(self, thread: Thread) -> str:
        """
        Получение информации о мастерах
        
        Returns:
            Отформатированная информация о мастерах в удобном читаемом формате
        """
        try:
            data = _masters_data_loader.load_data()
            
            if not data:
                return "Информация о мастерах не найдена"
            
            # Форматируем данные в удобный читаемый формат
            formatter = MastersFormatter()
            result = formatter.format_masters(data)
            
            return result
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при получении информации о мастерах: {e}", exc_info=True)
                return format_system_error(e, "получение информации о мастерах")
            else:
                logger.error(f"Неожиданная ошибка при получении информации о мастерах: {e}", exc_info=True)
                return format_system_error(e, "получение информации о мастерах")

