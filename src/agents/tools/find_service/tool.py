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
from .category_enricher import enrich_services_with_categories

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class FindService(BaseModel):
    """
    Find services by name. Search is performed by similar names, does not require exact match.
    If a master name is specified, it searches for a master by name and service, returning information about the master and their services.
    """
    
    service_name: str = Field(
        description="Service name to search for (text)"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Master name (optional field). If specified, searches for a master by name and service"
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
        
        # Блок услуг Топ-мастера (продолжаем нумерацию с конца списка Мастера)
        if top_master_services:
            result_lines.append(f"{category_name} - Топ-мастер:")
            # Начинаем нумерацию с количества услуг Мастера + 1
            start_number = len(master_services) + 1
            for index, service in enumerate(top_master_services, start=start_number):
                name = service.get('name', 'Неизвестно')
                price = service.get('prices', 'Не указана')
                service_id = service.get('id', 'Не указан')
                result_lines.append(f"{index}. {name} (ID: {service_id}) - {price} руб.")
        
        # Добавляем инструкцию в конце
        result_lines.append("")
        result_lines.append("((Если можешь выбрать конкретную услугу, верни ТОЛЬКО JSON с ID выбранной услуги в формате: {{'service_id': 12345678}}))\n ((Строго сохраняй форматирование))\n\n((Формулировка: 'Предлагаем следующие варианты: [полный список услуг с ценами], в том числе сделай два отдельных списка для мастер и топ-мастер'))")
        
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
        result_lines.append("((Если можешь выбрать конкретную услугу, верни ТОЛЬКО JSON с ID выбранной услуги в формате: {{'service_id': 12345678}}))\n ((Строго сохраняй форматирование))\n\n((Формулировка: 'Предлагаем следующие варианты: [полный список услуг с ценами]'))")
        
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
                async def process_master_search():
                    result = await find_master_by_service_logic(
                        yclients_service=yclients_service,
                        master_name=self.master_name,
                        service_name=self.service_name
                    )
                    
                    if not result.get('success'):
                        return None, None, result.get('error', 'Неизвестная ошибка')
                    
                    master = result.get('master', {})
                    master_name_result = master.get('name', '')
                    services = result.get('services', [])
                    
                    if not services:
                        return master_name_result, None, f"Мастер {master_name_result} найден, но у него нет доступных услуг."
                    
                    # Ограничиваем до 15 услуг
                    services = services[:15]
                    
                    # Обогащаем услуги информацией о категориях (для услуг с одинаковыми названиями)
                    services = await enrich_services_with_categories(yclients_service, services)
                    
                    return master_name_result, services, None
                
                master_name_result, services, error = asyncio.run(process_master_search())
                
                if error:
                    return error
                
                if not services:
                    return f"Мастер {master_name_result} найден, но у него нет доступных услуг."
                
                # Форматируем результат как нумерованный список (максимум 15 самых релевантных)
                result_lines = []
                
                for idx, service in enumerate(services, start=1):
                    title = service.get('title', 'Неизвестно')
                    category_title = service.get('category_title')
                    
                    # Если есть название категории, добавляем его к названию услуги
                    if category_title:
                        title = f"{title} ({category_title})"
                    
                    service_id = service.get('id', 'Не указан')
                    price = service.get('price', 'Не указана')
                    
                    result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
                
                # Добавляем инструкцию в конце
                result_lines.append("")
                result_lines.append("((Если можешь выбрать конкретную услугу, верни ТОЛЬКО JSON с ID выбранной услуги в формате: {{'service_id': 12345678}}))\n ((Строго сохраняй форматирование))\n\n((Формулировка: 'Предлагаем следующие варианты: [полный список услуг с ценами]'))")
                
                return "\n".join(result_lines)
            
            # Обычный поиск услуг
            async def process_service_search():
                result = await find_service_logic(
                    yclients_service=yclients_service,
                    service_name=self.service_name
                )
                
                if not result.get('success'):
                    return None, result.get('error', 'Неизвестная ошибка')
                
                services = result.get('services', [])
                
                if not services:
                    return None, f"Услуги с названием '{self.service_name}' не найдены"
                
                # Ограничиваем до 15 услуг
                services = services[:15]
                
                # Обогащаем услуги информацией о категориях (для услуг с одинаковыми названиями)
                services = await enrich_services_with_categories(yclients_service, services)
                
                return services, None
            
            services, error = asyncio.run(process_service_search())
            
            if error:
                return f"Ошибка: {error}" if not error.startswith("Услуги") else error
            
            if not services:
                return f"Услуги с названием '{self.service_name}' не найдены"
            
            # Форматируем результат
            result_lines = []
            
            for idx, service in enumerate(services, start=1):
                title = service.get('title', 'Неизвестно')
                category_title = service.get('category_title')
                
                # Если есть название категории, добавляем его к названию услуги
                if category_title:
                    title = f"{title} ({category_title})"
                
                service_id = service.get('id', 'Не указан')
                price = service.get('price', 'Не указана')
                
                result_lines.append(f"{idx}. {title} (ID: {service_id}) - {price} руб.")
            
            # Добавляем инструкцию в конце
            result_lines.append("")
            result_lines.append("((Если можешь выбрать конкретную услугу, верни ТОЛЬКО JSON с ID выбранной услуги в формате: {{'service_id': 12345678}}))\n ((Строго сохраняй форматирование))\n\n((Формулировка: 'Предлагаем следующие варианты: [полный список услуг с ценами]'))")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске услуг: {e}", exc_info=True)
            return f"Ошибка при поиске услуг: {str(e)}"

