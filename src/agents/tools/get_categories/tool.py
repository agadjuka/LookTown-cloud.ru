"""
Инструмент для получения списка категорий услуг
"""
import json
from pydantic import BaseModel
from ....common.thread import Thread

from ..common.services_data_loader import _data_loader
from ..common.error_handler import handle_technical_errors, format_system_error, is_technical_error

try:
    from ....services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class GetCategories(BaseModel):
    """
    Get a list of all service categories with their IDs.
    """
    
    @handle_technical_errors("получение списка категорий")
    def process(self, thread: Thread) -> str:
        """
        Получение списка всех категорий услуг
        
        Returns:
            Отформатированный список категорий с ID
        """
        try:
            data = _data_loader.load_data()
            
            if not data:
                return "Категории услуг не найдены"
            
            categories = []
            for cat_id, cat_data in sorted(data.items(), key=lambda x: int(x[0])):
                category_name = cat_data.get('category_name', 'Неизвестно')
                categories.append(f"{cat_id}. {category_name}")
            
            result = "Доступные категории услуг:\n\n" + "\n".join(categories)
            result += "\n\n((Сохраняй форматирование))"
            
            return result
            
        except Exception as e:
            if is_technical_error(e):
                logger.error(f"Техническая ошибка при получении категорий: {e}", exc_info=True)
                return format_system_error(e, "получение списка категорий")
            else:
                logger.error(f"Неожиданная ошибка при получении категорий: {e}", exc_info=True)
                return format_system_error(e, "получение списка категорий")

