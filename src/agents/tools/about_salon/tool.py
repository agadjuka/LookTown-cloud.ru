"""
Инструмент для получения информации о салоне
"""
import json
from pydantic import BaseModel
from ....common.thread import Thread

from ..common.about_salon_data_loader import _about_salon_data_loader
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error

try:
    from ....services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class AboutSalon(BaseModel):
    """
    Get complete information about the salon.
    Use when the client asks "расскажите о салоне", "что такое LookTown", "где вы находитесь" or similar questions about the salon.
    """
    
    @handle_technical_errors("получение информации о салоне")
    def process(self, thread: Thread) -> str:
        """
        Получение информации о салоне
        
        Returns:
            Полный текст информации о салоне
        """
        try:
            data = _about_salon_data_loader.load_data()
            
            if not data:
                return "Информация о салоне не найдена"
            
            text = data.get('text', '')
            
            if not text:
                return "Информация о салоне пуста"
            
            return text
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при получении информации о салоне: {e}", exc_info=True)
                return format_system_error(e, "получение информации о салоне")
            else:
                logger.error(f"Неожиданная ошибка при получении информации о салоне: {e}", exc_info=True)
                return format_system_error(e, "получение информации о салоне")

