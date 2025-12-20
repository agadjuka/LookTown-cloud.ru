"""
Модуль для обогащения услуг информацией о категориях
"""
import asyncio
from typing import Dict, List, Optional
from ..common.yclients_service import YclientsService


async def get_category_title(
    yclients_service: YclientsService,
    category_id: int
) -> Optional[str]:
    """
    Получает название категории по её ID
    
    Args:
        yclients_service: Сервис для работы с API
        category_id: ID категории
        
    Returns:
        Название категории или None, если не удалось получить
    """
    try:
        url = f"https://api.yclients.com/api/v1/service_category/{yclients_service.company_id}/{category_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": yclients_service.auth_header,
            "Content-Type": "application/json"
        }
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if not response.ok:
                    return None
                
                response_data = await response.json()
                # API может возвращать данные в поле 'data' или напрямую
                category_data = response_data.get('data', response_data)
                
                # Извлекаем title категории
                if isinstance(category_data, dict):
                    # Пробуем разные возможные поля для названия категории
                    title = category_data.get('title') or category_data.get('name') or category_data.get('category_name')
                    return title
                
                return None
                
    except Exception:
        return None


async def enrich_services_with_categories(
    yclients_service: YclientsService,
    services: List[Dict]
) -> List[Dict]:
    """
    Обогащает услуги информацией о категориях для услуг с одинаковыми названиями
    
    Args:
        yclients_service: Сервис для работы с API
        services: Список услуг с полями 'id', 'title', 'price'
        
    Returns:
        Список услуг с добавленным полем 'category_title' (если нужно)
    """
    if not services:
        return services
    
    # Группируем услуги по названию
    services_by_title: Dict[str, List[Dict]] = {}
    for service in services:
        title = service.get('title', '')
        if title not in services_by_title:
            services_by_title[title] = []
        services_by_title[title].append(service)
    
    # Находим услуги с одинаковыми названиями (больше 1 услуги с таким названием)
    duplicate_titles = {title: service_list for title, service_list in services_by_title.items() 
                        if len(service_list) > 1}
    
    if not duplicate_titles:
        # Если нет дубликатов, возвращаем как есть
        return services
    
    # Собираем все ID услуг с дублирующимися названиями
    duplicate_service_ids = []
    service_id_to_service = {}
    
    for service_list in duplicate_titles.values():
        for service in service_list:
            service_id = service.get('id')
            if service_id:
                duplicate_service_ids.append(service_id)
                service_id_to_service[service_id] = service
    
    # Параллельно получаем детали всех услуг с дублирующимися названиями
    tasks = [
        yclients_service.get_service_details(service_id)
        for service_id in duplicate_service_ids
    ]
    
    service_details_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Собираем уникальные category_id
    category_ids_to_fetch = set()
    service_id_to_category_id = {}
    
    for idx, service_details in enumerate(service_details_list):
        if isinstance(service_details, Exception):
            continue
        
        if idx >= len(duplicate_service_ids):
            continue
        
        service_id = duplicate_service_ids[idx]
        category_id = service_details.category_id
        
        if category_id:
            service_id_to_category_id[service_id] = category_id
            category_ids_to_fetch.add(category_id)
    
    if not category_ids_to_fetch:
        # Если не удалось получить category_id, возвращаем как есть
        return services
    
    # Параллельно получаем названия категорий
    tasks = [
        get_category_title(yclients_service, category_id)
        for category_id in category_ids_to_fetch
    ]
    
    category_titles = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Создаем кэш category_id -> title
    category_cache: Dict[int, Optional[str]] = {}
    category_ids_list = list(category_ids_to_fetch)
    
    for idx, category_id in enumerate(category_ids_list):
        if idx < len(category_titles):
            title = category_titles[idx]
            if not isinstance(title, Exception) and title:
                category_cache[category_id] = title
    
    # Обогащаем услуги информацией о категориях
    enriched_services = []
    
    for service in services:
        service_id = service.get('id')
        service_title = service.get('title', '')
        
        # Если это услуга с дублирующимся названием, добавляем категорию
        if service_title in duplicate_titles and service_id in service_id_to_category_id:
            category_id = service_id_to_category_id[service_id]
            if category_id in category_cache:
                category_title = category_cache[category_id]
                if category_title:
                    # Сохраняем название категории
                    service['category_title'] = category_title
        
        enriched_services.append(service)
    
    return enriched_services

