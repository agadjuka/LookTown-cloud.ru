"""
Инструмент для получения списка услуг категории
"""
import json
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.services_data_loader import _data_loader

try:
    from ....services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class GetServices(BaseModel):
    """
    Получить список услуг указанной категории с ценами и ID услуг.
    """
    
    category_id: str = Field(
        description="ID категории (строка). Доступные категории: '1' - Маникюр, '2' - Педикюр, '3' - Услуги для мужчин, '4' - Брови, '5' - Ресницы, '6' - Макияж, '7' - Парикмахерские услуги, '8' - Пирсинг, '9' - Лазерная эпиляция, '10' - Косметология, '11' - Депиляция, '12' - Массаж, '13' - LOOKTOWN SPA."
    )
    
    def _format_services_with_master_levels(self, category_name: str, services: list) -> str:
        """
        Форматирование услуг с разделением по уровням мастеров для категорий Маникюр и Педикюр
        """
        # Разделяем услуги по уровням мастеров
        master_services = []
        top_master_services = []
        
        for service in services:
            master_level = service.get('master_level', '')
            if master_level == 'Топ-мастер':
                top_master_services.append(service)
            else:
                master_services.append(service)
        
        result_lines = []
        
        # Блок услуг Мастера
        if master_services:
            result_lines.append(f"{category_name} - Мастер:")
            for index, service in enumerate(master_services, start=1):
                name = service.get('name', 'Неизвестно')
                price = service.get('prices', 'Не указана')
                service_id = service.get('id', 'Не указан')
                result_lines.append(f"{index}. {name} (ID: {service_id}) - {price} руб.")
            result_lines.append("")  # Пустая строка между блоками
        
        # Блок услуг Топ-мастера
        if top_master_services:
            result_lines.append(f"{category_name} - Топ-мастер:")
            for index, service in enumerate(top_master_services, start=1):
                name = service.get('name', 'Неизвестно')
                price = service.get('prices', 'Не указана')
                service_id = service.get('id', 'Не указан')
                result_lines.append(f"{index}. {name} (ID: {service_id}) - {price} руб.")
        
        # Добавляем инструкцию в конце
        result_lines.append("")
        result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
        
        return "\n".join(result_lines)
    
    def _format_services_simple(self, category_name: str, services: list) -> str:
        """
        Простое форматирование услуг для остальных категорий
        """
        result_lines = [f"Услуги категории '{category_name}':\n"]
        
        for index, service in enumerate(services, start=1):
            name = service.get('name', 'Неизвестно')
            price = service.get('prices', 'Не указана')
            master_level = service.get('master_level')
            service_id = service.get('id', 'Не указан')
            
            service_line = f"{index}. {name} (ID: {service_id}) - {price} руб."
            if master_level:
                service_line += f" ({master_level})"
            
            result_lines.append(service_line)
        
        # Добавляем инструкцию в конце
        result_lines.append("")
        result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
        
        return "\n".join(result_lines)
    
    def process(self, thread: Thread) -> str:
        """
        Получение списка услуг указанной категории
        
        Args:
            category_id: ID категории из списка категорий
            
        Returns:
            Отформатированный список услуг категории
        """
        try:
            data = _data_loader.load_data()
            
            if not data:
                return "Данные об услугах не найдены"
            
            # Получаем категорию по ID
            category = data.get(self.category_id)
            if not category:
                available_ids = ", ".join(sorted(data.keys(), key=int))
                return (
                    f"Категория с ID '{self.category_id}' не найдена.\n"
                    f"Доступные ID категорий: {available_ids}\n"
                    f"Используйте GetCategories для получения полного списка категорий."
                )
            
            category_name = category.get('category_name', 'Неизвестно')
            services = category.get('services', [])
            
            if not services:
                return f"В категории '{category_name}' нет доступных услуг"
            
            # Для категорий Маникюр (1) и Педикюр (2) разделяем по уровням мастеров
            if self.category_id in ['1', '2']:
                return self._format_services_with_master_levels(category_name, services)
            else:
                # Для остальных категорий - обычный список
                return self._format_services_simple(category_name, services)
            
        except FileNotFoundError as e:
            logger.error(f"Файл с услугами не найден: {e}")
            return "Файл с данными об услугах не найден"
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return "Ошибка при чтении данных об услугах"
        except Exception as e:
            logger.error(f"Ошибка при получении услуг: {e}")
            return f"Ошибка при получении услуг: {str(e)}"
