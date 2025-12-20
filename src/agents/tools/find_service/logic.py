"""
Логика для поиска услуг по названию и мастера по имени и услуге
"""
import asyncio
from typing import Dict, List, Any, Optional
from ..common.yclients_service import YclientsService
from ..common.service_master_mapper import get_service_master_mapper
from ..common.book_times_logic import _normalize_name, _get_name_variants


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


def _is_service_similar(service_title: str, search_query: str) -> bool:
    """
    Проверяет, похоже ли название услуги на поисковый запрос
    
    Args:
        service_title: Название услуги
        search_query: Поисковый запрос
        
    Returns:
        True если услуга похожа на запрос
    """
    if not service_title or not search_query:
        return False
    
    normalized_title = _normalize_text(service_title)
    normalized_query = _normalize_text(search_query)
    
    # Точное совпадение
    if normalized_title == normalized_query:
        return True
    
    # Поисковый запрос содержится в названии услуги
    if normalized_query in normalized_title:
        return True
    
    # Название услуги содержится в поисковом запросе
    if normalized_title in normalized_query:
        return True
    
    # Проверяем совпадение по словам (если хотя бы одно слово совпадает)
    query_words = set(normalized_query.split())
    title_words = set(normalized_title.split())
    
    # Если есть пересечение слов (исключая очень короткие слова)
    common_words = query_words & title_words
    meaningful_words = {w for w in common_words if len(w) > 2}
    
    if meaningful_words:
        return True
    
    return False


async def find_service_logic(
    yclients_service: YclientsService,
    service_name: str
) -> Dict[str, Any]:
    """
    Основная логика поиска услуг по названию
    
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
        
        # Ищем похожие услуги
        matching_services = []
        for service in all_services:
            # Проверяем активность услуги
            if not service.get('active', 1):
                continue
            
            # Получаем название услуги
            service_title = service.get('title', '') or service.get('name', '')
            if not service_title:
                continue
            
            # Проверяем похожесть
            if _is_service_similar(service_title, service_name):
                service_id = service.get('id')
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
        
        if not matching_services:
            return {
                "success": False,
                "error": f"Услуги с названием '{service_name}' не найдены",
                "services": []
            }
        
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
    
    Args:
        service_title: Название услуги
        search_query: Поисковый запрос
        
    Returns:
        float: Оценка релевантности (чем выше, тем релевантнее)
    """
    if not service_title or not search_query:
        return 0.0
    
    normalized_title = _normalize_text(service_title)
    normalized_query = _normalize_text(search_query)
    
    # Точное совпадение - максимальная релевантность
    if normalized_title == normalized_query:
        return 100.0
    
    # Поисковый запрос полностью содержится в названии услуги
    if normalized_query in normalized_title:
        # Чем ближе к началу, тем выше релевантность
        position = normalized_title.find(normalized_query)
        relevance = 80.0 - (position * 0.1)  # Штраф за позицию
        return max(relevance, 50.0)
    
    # Название услуги полностью содержится в поисковом запросе
    if normalized_title in normalized_query:
        return 60.0
    
    # Совпадение по словам
    query_words = set(normalized_query.split())
    title_words = set(normalized_title.split())
    
    # Исключаем очень короткие слова
    meaningful_query_words = {w for w in query_words if len(w) > 2}
    meaningful_title_words = {w for w in title_words if len(w) > 2}
    
    if not meaningful_query_words or not meaningful_title_words:
        return 0.0
    
    # Вычисляем процент совпадающих слов
    common_words = meaningful_query_words & meaningful_title_words
    if common_words:
        # Процент совпадения слов
        word_match_ratio = len(common_words) / len(meaningful_query_words)
        # Базовая релевантность на основе совпадения слов
        base_relevance = word_match_ratio * 50.0
        
        # Бонус если все слова запроса найдены
        if len(common_words) == len(meaningful_query_words):
            base_relevance += 20.0
        
        return base_relevance
    
    return 0.0


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
        
        # 2. Находим всех кандидатов по имени
        mapper = get_service_master_mapper()
        search_variants = _get_name_variants(master_name)
        normalized_search = _normalize_name(master_name)
        
        candidates = []
        for staff in staff_list:
            staff_name = staff.get("name", "")
            if not staff_name or staff_name == "Лист ожидания":
                continue
            
            normalized_staff_name = _normalize_name(staff_name)
            
            # Проверяем точное совпадение
            if normalized_staff_name == normalized_search:
                candidates.append(staff)
                continue
            
            # Проверяем варианты имени
            staff_variants = _get_name_variants(staff_name)
            if any(variant in search_variants for variant in staff_variants):
                candidates.append(staff)
                continue
            
            # Проверяем частичное совпадение
            if normalized_search in normalized_staff_name or normalized_staff_name in normalized_search:
                candidates.append(staff)
        
        if not candidates:
            return {
                "success": False,
                "error": f"Мастер с именем '{master_name}' не найден"
            }
        
        # 3. Если найден только один кандидат, возвращаем его
        if len(candidates) == 1:
            found_master = candidates[0]
        else:
            # 4. Если несколько кандидатов, фильтруем по услуге
            # Сначала проверяем по должности
            suitable_candidates = []
            for candidate in candidates:
                position = candidate.get("position", {})
                position_title = position.get("title", "") if position else ""
                position_description = position.get("description", "") if position else ""
                specialization = candidate.get("specialization", "")
                
                if mapper.is_master_suitable(
                    position_title, 
                    service_name,
                    position_description,
                    specialization
                ):
                    suitable_candidates.append(candidate)
            
            # Если нашли подходящих по должности, проверяем их услуги
            if suitable_candidates:
                # Проверяем, у кого из подходящих есть услуги из нужной категории
                best_candidate = None
                for candidate in suitable_candidates:
                    if await _check_master_has_service_category(yclients_service, candidate, service_name):
                        best_candidate = candidate
                        break
                
                if best_candidate:
                    found_master = best_candidate
                else:
                    # Если не нашли по услугам, берем первого подходящего по должности
                    found_master = suitable_candidates[0]
            else:
                # Если не нашли по должности, проверяем услуги всех кандидатов
                best_candidate = None
                for candidate in candidates:
                    if await _check_master_has_service_category(yclients_service, candidate, service_name):
                        best_candidate = candidate
                        break
                
                if best_candidate:
                    found_master = best_candidate
                else:
                    # Если ничего не нашли, возвращаем первого кандидата
                    found_master = candidates[0]
        
        master_id = found_master.get("id")
        master_name_result = found_master.get("name", "")
        position = found_master.get("position", {})
        position_title = position.get("title", "") if position else ""
        
        # 5. Получаем список услуг мастера из services_links
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
        
        # 7. Формируем список услуг с релевантностью
        services_with_relevance = []
        for idx, service_details in enumerate(service_details_list):
            if isinstance(service_details, Exception):
                continue
            
            if idx >= len(service_ids):
                continue
            
            service_id = service_ids[idx]
            service_title = service_details.get_title()
            if service_title == "Лист ожидания":
                continue
            
            # Вычисляем релевантность услуги к поисковому запросу
            relevance = _calculate_service_relevance(service_title, service_name)
            
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
            
            services_with_relevance.append({
                "id": service_id,
                "title": service_title,
                "duration": service_details.duration,
                "price": price,
                "relevance": relevance
            })
        
        if not services_with_relevance:
            return {
                "success": False,
                "error": f"Не удалось получить детали услуг мастера {master_name_result}"
            }
        
        # 8. Сортируем услуги по релевантности (от большей к меньшей) и берем топ-10
        services_with_relevance.sort(key=lambda x: x["relevance"], reverse=True)
        top_services = services_with_relevance[:10]
        
        # Убираем поле relevance из результата
        services = [
            {
                "id": s["id"],
                "title": s["title"],
                "duration": s["duration"],
                "price": s["price"]
            }
            for s in top_services
        ]
        
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

