"""
Логика для поиска услуг по названию
"""
from typing import Dict, List, Any
from ..common.yclients_service import YclientsService


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

