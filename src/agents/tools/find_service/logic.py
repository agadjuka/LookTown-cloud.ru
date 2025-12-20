"""
Логика для поиска услуг по названию и мастера по имени и услуге
"""
import asyncio
from typing import Dict, List, Any, Optional
from ..common.yclients_service import YclientsService
from ..common.service_master_mapper import get_service_master_mapper
from ..common.book_times_logic import _normalize_name, _get_name_variants
from .service_matcher import ServiceMatcher

# Создаем глобальный экземпляр матчера (он переиспользуется для всех запросов)
_service_matcher = ServiceMatcher()


def _normalize_text(text: str) -> str:
    """
    Нормализует текст для сравнения: приводит к нижнему регистру и убирает лишние пробелы
    
    Args:
        text: Текст для нормализации
        
    Returns:
        Нормализованный текст
    """
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


async def find_service_logic(
    yclients_service: YclientsService,
    service_name: str
) -> Dict[str, Any]:
    """
    Основная логика поиска услуг по названию с использованием умного поиска
    
    Args:
        yclients_service: Сервис для работы с API
        service_name: Название услуги для поиска
        
    Returns:
        Dict: Результат поиска с информацией о найденных услугах
    """
    try:
        # Получаем список всех услуг
        all_services = await yclients_service.get_all_services()
        
        if not all_services:
            return {
                "success": False,
                "error": "Не удалось получить список услуг",
                "services": []
            }
        
        # Фильтруем только активные услуги
        active_services = [
            service for service in all_services 
            if service.get('active', 1) and (service.get('title') or service.get('name'))
        ]
        
        if not active_services:
            return {
                "success": False,
                "error": "Не найдено активных услуг",
                "services": []
            }
        
        # Используем умный поиск для нахождения наиболее релевантных услуг
        # Минимальная релевантность 50% для включения в результат (повышено для фильтрации лишнего)
        matches = _service_matcher.find_best_matches(
            active_services,
            service_name,
            min_relevance=50.0,
            max_results=15
        )
        
        if not matches:
            return {
                "success": False,
                "error": f"Услуги с названием '{service_name}' не найдены",
                "services": []
            }
        
        # Формируем результат
        matching_services = []
        for service, relevance in matches:
            service_id = service.get('id')
            service_title = service.get('title', '') or service.get('name', '')
            price_min = service.get('price_min')
            price_max = service.get('price_max')
            
            # Формируем цену
            if price_min is not None and price_max is not None:
                if price_min == price_max:
                    price = f"{int(price_min)}"
                else:
                    price = f"{int(price_min)} - {int(price_max)}"
            elif price_min is not None:
                price = f"{int(price_min)}"
            elif price_max is not None:
                price = f"{int(price_max)}"
            else:
                price = "Не указана"
            
            matching_services.append({
                "id": service_id,
                "title": service_title,
                "price": price
            })
        
        return {
            "success": True,
            "services": matching_services,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при поиске услуг: {str(e)}",
            "services": []
        }


async def _check_master_has_service_category(
    yclients_service: YclientsService,
    master: Dict[str, Any],
    service_name: str
) -> bool:
    """
    Проверяет, есть ли у мастера услуги из нужной категории
    
    Args:
        yclients_service: Сервис для работы с API
        master: Данные мастера
        service_name: Название услуги
        
    Returns:
        bool: True если у мастера есть услуги из нужной категории
    """
    try:
        from ..common.services_data_loader import _data_loader
        
        # Получаем категорию услуги из services.json
        services_data = _data_loader.load_data()
        service_name_lower = service_name.lower()
        
        # Ищем категорию услуги
        target_category = None
        for category_id, category_data in services_data.items():
            category_name = category_data.get("category_name", "").lower()
            if service_name_lower in category_name or category_name in service_name_lower:
                target_category = category_id
                break
            
            # Проверяем услуги в категории
            services = category_data.get("services", [])
            for service in services:
                service_name_in_cat = service.get("name", "").lower()
                if service_name_lower in service_name_in_cat or service_name_in_cat in service_name_lower:
                    target_category = category_id
                    break
            
            if target_category:
                break
        
        if not target_category:
            return False
        
        # Получаем ID услуг из категории
        category_data = services_data.get(target_category, {})
        category_services = category_data.get("services", [])
        category_service_ids = {str(service.get("id", "")) for service in category_services}
        
        # Проверяем, есть ли у мастера услуги из этой категории
        services_links = master.get("services_links", [])
        master_service_ids = {str(link.get("service_id", "")) for link in services_links}
        
        # Проверяем пересечение
        return bool(category_service_ids & master_service_ids)
        
    except Exception:
        return False


def _calculate_service_relevance(service_title: str, search_query: str) -> float:
    """
    Вычисляет релевантность услуги к поисковому запросу
    Использует умный поиск с морфологическим анализом
    
    Args:
        service_title: Название услуги
        search_query: Поисковый запрос
        
    Returns:
        float: Оценка релевантности (чем выше, тем релевантнее)
    """
    return _service_matcher.calculate_relevance(service_title, search_query)


async def find_master_by_service_logic(
    yclients_service: YclientsService,
    master_name: str,
    service_name: str
) -> Dict[str, Any]:
    """
    Основная логика поиска мастера по имени и услуге
    
    Args:
        yclients_service: Сервис для работы с API
        master_name: Имя мастера (может быть неточным)
        service_name: Название услуги (может быть неточным)
        
    Returns:
        Dict: Результат поиска с информацией о мастере и его услугах
    """
    try:
        # 1. Получаем список всех мастеров
        staff_list = await yclients_service.get_staff_list()
        
        if not staff_list:
            return {
                "success": False,
                "error": "Не удалось получить список мастеров"
            }
        
        # 2. Находим всех кандидатов по имени с использованием умного поиска
        mapper = get_service_master_mapper()
        
        # Используем умный поиск для нахождения наиболее релевантных мастеров
        master_matches = _service_matcher.find_best_masters(
            staff_list,
            master_name,
            min_relevance=30.0,
            max_results=10
        )
        
        if not master_matches:
            return {
                "success": False,
                "error": f"Мастер с именем '{master_name}' не найден"
            }
        
        # 3. Фильтруем кандидатов по максимальной релевантности имени
        if not master_matches:
            return {
                "success": False,
                "error": f"Мастер с именем '{master_name}' не найден"
            }
        
        # Находим максимальную релевантность
        max_relevance = max(relevance for _, relevance in master_matches)
        
        # Оставляем только мастеров с максимальной релевантностью
        top_candidates = [(master, relevance) for master, relevance in master_matches if relevance == max_relevance]
        
        # Переменная для сохранения найденных услуг (если уже найдены при выборе мастера)
        pre_found_services = None
        
        # Если только один кандидат с максимальной релевантностью
        if len(top_candidates) == 1:
            found_master, _ = top_candidates[0]
        else:
            # 4. Если несколько кандидатов с максимальной релевантностью, проверяем их услуги
            # Для каждого мастера получаем услуги и ищем релевантные
            best_master = None
            best_services_count = 0
            best_services = []
            
            for candidate_master, _ in top_candidates:
                # Получаем услуги мастера
                services_links = candidate_master.get("services_links", [])
                if not services_links:
                    continue
                
                service_ids = [link.get("service_id") for link in services_links if link.get("service_id")]
                if not service_ids:
                    continue
                
                # Получаем детали услуг
                tasks = [
                    yclients_service.get_service_details(service_id)
                    for service_id in service_ids
                ]
                service_details_list = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Формируем список услуг
                candidate_services_list = []
                for idx, service_details in enumerate(service_details_list):
                    if isinstance(service_details, Exception):
                        continue
                    
                    if idx >= len(service_ids):
                        continue
                    
                    service_id = service_ids[idx]
                    service_title = service_details.get_title()
                    if service_title == "Лист ожидания":
                        continue
                    
                    price_min = service_details.price_min
                    price_max = service_details.price_max
                    
                    if price_min is not None and price_max is not None:
                        if price_min == price_max:
                            price = f"{int(price_min)}"
                        else:
                            price = f"{int(price_min)} - {int(price_max)}"
                    elif price_min is not None:
                        price = f"{int(price_min)}"
                    elif price_max is not None:
                        price = f"{int(price_max)}"
                    else:
                        price = "Не указана"
                    
                    candidate_services_list.append({
                        "id": service_id,
                        "title": service_title,
                        "duration": service_details.duration,
                        "price": price
                    })
                
                if not candidate_services_list:
                    continue
                
                # Ищем релевантные услуги у этого мастера
                service_matches = _service_matcher.find_best_matches(
                    candidate_services_list,
                    service_name,
                    min_relevance=30.0,
                    max_results=15
                )
                
                # Считаем количество релевантных услуг
                relevant_services_count = len(service_matches)
                
                # Выбираем мастера с наибольшим количеством релевантных услуг
                if relevant_services_count > best_services_count:
                    best_master = candidate_master
                    best_services_count = relevant_services_count
                    best_services = [service for service, _ in service_matches]
            
            # Если нашли мастера с релевантными услугами
            if best_master:
                found_master = best_master
                # Сохраняем найденные услуги для дальнейшего использования
                pre_found_services = best_services
            else:
                # Если ни у кого нет релевантных услуг, берем первого кандидата
                found_master = top_candidates[0][0]
                pre_found_services = None
        
        master_id = found_master.get("id")
        master_name_result = found_master.get("name", "")
        position = found_master.get("position", {})
        position_title = position.get("title", "") if position else ""
        
        # 5. Если услуги уже найдены при выборе мастера, используем их
        if pre_found_services is not None:
            services = pre_found_services
        else:
            # Иначе получаем услуги выбранного мастера
            services_links = found_master.get("services_links", [])
            
            if not services_links:
                return {
                    "success": False,
                    "error": f"У мастера {master_name_result} нет доступных услуг"
                }
            
            # 6. Параллельно получаем детали всех услуг
            service_ids = [link.get("service_id") for link in services_links if link.get("service_id")]
            
            if not service_ids:
                return {
                    "success": False,
                    "error": f"Не удалось получить список услуг мастера {master_name_result}"
                }
            
            tasks = [
                yclients_service.get_service_details(service_id)
                for service_id in service_ids
            ]
            
            service_details_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 7. Формируем список услуг для умного поиска
            services_list = []
            for idx, service_details in enumerate(service_details_list):
                if isinstance(service_details, Exception):
                    continue
                
                if idx >= len(service_ids):
                    continue
                
                service_id = service_ids[idx]
                service_title = service_details.get_title()
                if service_title == "Лист ожидания":
                    continue
                
                # Получаем цену услуги
                price_min = service_details.price_min
                price_max = service_details.price_max
                
                # Формируем цену
                if price_min is not None and price_max is not None:
                    if price_min == price_max:
                        price = f"{int(price_min)}"
                    else:
                        price = f"{int(price_min)} - {int(price_max)}"
                elif price_min is not None:
                    price = f"{int(price_min)}"
                elif price_max is not None:
                    price = f"{int(price_max)}"
                else:
                    price = "Не указана"
                
                services_list.append({
                    "id": service_id,
                    "title": service_title,
                    "duration": service_details.duration,
                    "price": price
                })
            
            if not services_list:
                return {
                    "success": False,
                    "error": f"Не удалось получить детали услуг мастера {master_name_result}"
                }
            
            # 8. Используем умный поиск для нахождения наиболее релевантных услуг
            # Минимальная релевантность 30% для услуг мастера (ниже, чем для общего поиска)
            service_matches = _service_matcher.find_best_matches(
                services_list,
                service_name,
                min_relevance=30.0,
                max_results=15
            )
            
            # Извлекаем услуги из результатов поиска (уже отсортированы по релевантности)
            services = [service for service, relevance in service_matches]
            
            # Если не нашли услуги с умным поиском, но мастер найден - возвращаем все услуги мастера
            # (возможно, запрос был слишком общим или услуга называется по-другому)
            if not services and services_list:
                services = services_list[:15]  # Берем первые 15 услуг мастера
        
        # 9. Формируем успешный ответ
        return {
            "success": True,
            "master": {
                "id": master_id,
                "name": master_name_result,
                "position_title": position_title
            },
            "services": services
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при поиске мастера: {str(e)}"
        }

