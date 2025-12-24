"""
Модуль для обработки приветствий в первом сообщении
"""


def has_greeting(text: str) -> bool:
    """
    Проверяет, содержит ли текст приветствие
    
    Args:
        text: Текст для проверки
        
    Returns:
        True, если текст содержит приветствие, False иначе
    """
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    greetings = [
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "здравствуйте",
        "здравствуй",
        "привет",
        "приветствую",
        "доброго времени суток",
        "доброго дня",
        "доброго утра",
        "доброго вечера"
    ]
    
    # Проверяем начало текста
    for greeting in greetings:
        if text_lower.startswith(greeting):
            return True
    
    # Проверяем первые 50 символов
    text_start = text_lower[:50]
    for greeting in greetings:
        if greeting in text_start:
            return True
    
    return False


def add_greeting_if_needed(text: str, is_first_message: bool) -> str:
    """
    Добавляет приветствие "Добрый день!" в начало текста, если:
    1. Это первое сообщение пользователя
    2. В тексте еще нет приветствия
    
    Args:
        text: Текст сообщения от агента
        is_first_message: Флаг первого сообщения
        
    Returns:
        Текст с добавленным приветствием (если нужно) или исходный текст
    """
    if not text or not text.strip():
        return text
    
    if not is_first_message:
        return text
    
    if has_greeting(text):
        return text
    
    return f"Добрый день!\n\n{text}"
