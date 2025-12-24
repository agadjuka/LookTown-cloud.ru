"""
Инструмент для получения информации о мастерах
"""
from pydantic import BaseModel
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.masters_data_loader import _masters_data_loader
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
            
        except FileNotFoundError as e:
            logger.error(f"Файл с информацией о мастерах не найден: {e}")
            return "Файл с информацией о мастерах не найден"
        except Exception as e:
            logger.error(f"Ошибка при получении информации о мастерах: {e}")
            return f"Ошибка при получении информации о мастерах: {str(e)}"

