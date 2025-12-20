"""
Инструмент для поиска услуг по названию
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from ..common.services_data_loader import _data_loader
from .logic import find_service_logic, find_master_by_service_logic
from .category_matcher import find_category_by_query

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class FindService(BaseModel):
    """
    Найти услуги по названию. Поиск выполняется по похожим названиям, не требует точного совпадения.
    Если указано имя мастера, то ищет мастера по имени и услуге, возвращая информацию о мастере и его услугах.
    """
    
    service_name: str = Field(
        description="Название услуги для поиска (текст)"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (необязательное поле). Если указано, то ищет мастера по имени и услуге"
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
        result_lines.append("((Формулировка: 'У нас есть следующие виды (напр. маникюра): [полный список услуг с ценами]'))")
        
        return "\n".join(result_lines)
    
    def _get_category_services(self, category_id: str) -> str:
        """
        Получает список услуг категории (как GetServices)
        
        Args:
            category_id: ID категории
            
        Returns:
            Отформатированный список услуг категории
        """
        try:
            data = _data_loader.load_data()
            
            if not data:
                return "Данные об услугах не найдены"
            
            # Получаем категорию по ID
            category = data.get(category_id)
            if not category:
                return f"Категория с ID '{category_id}' не найдена."
            
            category_name = category.get('category_name', 'Неизвестно')
            services = category.get('services', [])
            
            if not services:
                return f"В категории '{category_name}' нет доступных услуг"
            
            # Для категорий Маникюр (1) и Педикюр (2) разделяем по уровням мастеров
            if category_id in ['1', '2']:
                return self._format_services_with_master_levels(category_name, services)
            else:
                # Для остальных категорий - обычный список
                return self._format_services_simple(category_name, services)
                
        except Exception as e:
            logger.error(f"Ошибка при получении услуг категории: {e}")
            return f"Ошибка при получении услуг категории: {str(e)}"
    
    def process(self, thread: Thread) -> str:
        """
        Поиск услуг по названию или мастера по имени и услуге
        
        Returns:
            Отформатированная информация о найденных услугах или мастере и его услугах
        """
        try:
            # Если имя мастера не указано, проверяем, является ли запрос категорией
            if not self.master_name:
                category_id = find_category_by_query(self.service_name)
                if category_id:
                    # Если это категория, возвращаем список услуг категории
                    return self._get_category_services(category_id)
            
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Если указано имя мастера, используем логику поиска мастера по услуге
            if self.master_name:
                result = asyncio.run(
                    find_master_by_service_logic(
                        yclients_service=yclients_service,
                        master_name=self.master_name,
                        service_name=self.service_name
                    )
                )
                
                if not result.get('success'):
                    error = result.get('error', 'Неизвестная ошибка')
                    return f"Ошибка: {error}"
                
                master = result.get('master', {})
                master_name_result = master.get('name', '')
                master_id = master.get('id', '')
                position_title = master.get('position_title', '')
                
                services = result.get('services', [])
                
                if not services:
                    return f"Мастер {master_name_result} найден, но у него нет доступных услуг."
                
                # Форматируем результат как нумерованный список (топ-10 самых релевантных)
                result_lines = []
                
                for idx, service in enumerate(services, start=1):
                    title = service.get('title', 'Неизвестно')
                    service_id = service.get('id', 'Не указан')
                    price = service.get('price', 'Не указана')
                    
                    result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
                
                # Добавляем инструкцию в конце
                result_lines.append("")
                result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
                
                return "\n".join(result_lines)
            
            # Обычный поиск услуг
            result = asyncio.run(
                find_service_logic(
                    yclients_service=yclients_service,
                    service_name=self.service_name
                )
            )
            
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
            services = result.get('services', [])
            
            if not services:
                return f"Услуги с названием '{self.service_name}' не найдены"
            
            # Форматируем результат
            result_lines = []
            
            for idx, service in enumerate(services, start=1):
                title = service.get('title', 'Неизвестно')
                service_id = service.get('id', 'Не указан')
                price = service.get('price', 'Не указана')
                
                result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
            
            # Добавляем инструкцию в конце
            result_lines.append("")
            result_lines.append("((Не отправляй клиенту ID, строго сохраняй форматирование))")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске услуг: {e}", exc_info=True)
            return f"Ошибка при поиске услуг: {str(e)}"

