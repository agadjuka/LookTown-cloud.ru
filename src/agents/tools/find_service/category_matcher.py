"""
Модуль для распознавания категорий услуг по тексту запроса
"""
from typing import Optional, Dict
from ..common.services_data_loader import _data_loader


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


def _get_category_keywords() -> Dict[str, list]:
    """
    Возвращает словарь ключевых слов для каждой категории
    
    Returns:
        Dict: {category_id: [keywords]}
    """
    return {
        "1": ["маникюр", "маник", "маникюра", "маникюру", "маникюром", "маникюре", 
              "ногти", "ногтей", "ногтям", "маникюрные", "маникюрная", "маникюрный",
              "услуги для ногтей", "услуги по маникюру", "на маникюр", "на маник"],
        "2": ["педикюр", "педик", "педикюра", "педикюру", "педикюром", "педикюре",
              "педикюрные", "педикюрная", "педикюрный", "стопы", "стоп", "стопам",
              "услуги для стоп", "услуги по педикюру", "на педикюр", "на педик"],
        "3": ["мужчин", "мужской", "мужские", "мужская", "мужским", "мужчинам", 
              "для мужчин", "мужские услуги", "мужчинам услуги"],
        "4": ["брови", "бровей", "бровь", "бровям", "бровями", "бровью", "бровям",
              "услуги для бровей", "услуги по бровям", "брови услуги", "на брови"],
        "5": ["ресницы", "ресниц", "реснич", "реснички", "ресничек", "ресничкам",
              "наращивание ресниц", "услуги для ресниц", "услуги по ресницам", "на ресницы"],
        "6": ["макияж", "макияжа", "макияжу", "макияже", "макияжем", "макияжный", 
              "макияжные", "макияжная", "услуги макияжа", "на макияж"],
        "7": ["парикмахер", "парикмахерские", "парикмахерская", "парикмахерский",
              "стрижка", "стрижку", "стрижки", "стрижкой", "стрижке", "волосы", 
              "волос", "волосам", "услуги парикмахера", "на стрижку"],
        "8": ["пирсинг", "пирсинга", "пирсингу", "пирсингом", "пирсинге", "на пирсинг"],
        "9": ["лазерная эпиляция", "лазерная", "эпиляция лазером", "лазером", 
              "лазерная эпиляция", "лазерной эпиляции", "на лазерную эпиляцию"],
        "10": ["косметология", "косметолог", "косметологи", "косметологические", 
               "косметолога", "косметологическая", "косметологический", "на косметологию"],
        "11": ["депиляция", "депиляции", "депиляцию", "депиляцией", "депиляции", "на депиляцию"],
        "12": ["массаж", "массажа", "массажу", "массажем", "массажи", "массажам", "на массаж"],
        "13": ["looktown spa", "spa", "спа", "looktown", "спа процедуры", "спа-процедуры", 
               "на spa", "на спа"]
    }


def _get_service_words() -> set:
    """
    Возвращает набор служебных слов, которые не считаются конкретизацией услуги
    
    Returns:
        set: Множество служебных слов
    """
    return {
        "на", "для", "по", "с", "в", "к", "от", "до", "из", "у", "о", "об",
        "услуги", "услуга", "услуг", "услугу", "услуге", "услугой",
        "хочу", "нужен", "нужна", "нужно", "нужны",
        "записаться", "записаться", "запись", "записи",
        "какие", "какая", "какое", "какие",
        "что", "как", "где", "когда"
    }


def _is_simple_category_query(query: str, category_name: str, keywords: list) -> bool:
    """
    Проверяет, является ли запрос простым запросом категории (без конкретизации)
    
    Args:
        query: Поисковый запрос
        category_name: Название категории
        keywords: Список ключевых слов категории
        
    Returns:
        True если запрос является простым запросом категории (без дополнительных слов)
    """
    normalized_query = _normalize_text(query)
    normalized_category = _normalize_text(category_name)
    service_words = _get_service_words()
    
    # Разбиваем запрос на слова
    query_words_list = normalized_query.split()
    query_words = set(query_words_list)
    
    # Убираем служебные слова (но сохраняем короткие важные слова типа "spa")
    important_short_words = {"spa", "спа"}
    meaningful_query_words = set()
    for w in query_words:
        if w not in service_words:
            # Сохраняем слова длиннее 2 символов или важные короткие слова
            if len(w) > 2 or w in important_short_words:
                meaningful_query_words.add(w)
    
    # Если после удаления служебных слов не осталось значимых слов - это не категория
    if not meaningful_query_words:
        return False
    
    # Проверяем точное совпадение с названием категории
    if normalized_query == normalized_category:
        return True
    
    # Собираем все значимые слова категории и ключевых слов
    important_short_words = {"spa", "спа"}
    category_words = set(normalized_category.split())
    meaningful_category_words = {w for w in category_words if w not in service_words and (len(w) > 2 or w in important_short_words)}
    
    # Собираем все значимые слова из всех ключевых слов категории
    all_category_meaningful_words = meaningful_category_words.copy()
    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        keyword_words = normalized_keyword.split()
        for w in keyword_words:
            if w not in service_words and (len(w) > 2 or w in important_short_words):
                all_category_meaningful_words.add(w)
    
    # Проверяем, все ли значимые слова запроса входят в слова категории
    # Если есть хотя бы одно слово, которого нет в категории - это конкретизированный запрос
    if not meaningful_query_words.issubset(all_category_meaningful_words):
        return False
    
    # Проверяем точное совпадение с ключевыми словами
    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if normalized_query == normalized_keyword:
            return True
    
    # Если все слова запроса входят в категорию - это простая категория
    return True


def find_category_by_query(query: str) -> Optional[str]:
    """
    Находит категорию по текстовому запросу.
    Возвращает ID категории только если запрос является простым запросом категории
    (без конкретизации, например "маникюр", "брови", но не "маникюр с укреплением").
    
    Args:
        query: Поисковый запрос пользователя
        
    Returns:
        Optional[str]: ID категории или None, если это не простая категория или категория не найдена
    """
    if not query:
        return None
    
    try:
        data = _data_loader.load_data()
        keywords_map = _get_category_keywords()
        
        # Проверяем каждую категорию
        for category_id, category_data in data.items():
            category_name = category_data.get('category_name', '')
            keywords = keywords_map.get(category_id, [])
            
            # Проверяем, является ли это простым запросом категории (без конкретизации)
            if _is_simple_category_query(query, category_name, keywords):
                return category_id
        
        return None
        
    except Exception:
        return None

