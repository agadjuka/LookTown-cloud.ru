"""
Модуль для обработки приветствий в первом сообщении
"""
from typing import Optional
from ..storage.checkpointer import get_postgres_checkpointer
from .logger_service import logger


async def is_first_user_message(chat_id: str) -> bool:
    """
    Проверяет, является ли текущее сообщение первым сообщением пользователя в диалоге.
    
    Учитывает, что внутри одной операции могут быть промежуточные AI сообщения (tool calls).
    Проверяет количество сообщений от пользователя в истории:
    - Если только одно сообщение от пользователя (текущее) - это первое сообщение
    - Если больше одного - значит есть предыдущие сообщения, это не первое
    
    Args:
        chat_id: ID чата в Telegram
        
    Returns:
        True, если это первое сообщение пользователя, False иначе
    """
    try:
        # Получаем telegram_user_id из chat_id
        try:
            telegram_user_id = int(chat_id)
        except ValueError:
            logger.error(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id")
            return False
        
        # Получаем историю из checkpointer
        async with get_postgres_checkpointer() as checkpointer:
            config = {"configurable": {"thread_id": str(telegram_user_id)}}
            
            # Получаем последнее состояние
            state_snapshot = await checkpointer.aget(config)
            
            if not state_snapshot:
                # Если состояния нет, значит это первое сообщение
                return True
            
            # Извлекаем messages из состояния
            values = state_snapshot.values if hasattr(state_snapshot, 'values') else state_snapshot.get('values', {})
            messages = values.get("messages", [])
            
            if not messages:
                # Если сообщений нет, значит это первое
                return True
            
            # Подсчитываем сообщения от пользователя
            # В момент проверки в истории уже есть текущее сообщение пользователя
            # Если есть предыдущие сообщения от пользователя, значит это не первое сообщение
            user_messages_count = 0
            
            for msg in messages:
                # Получаем тип сообщения
                msg_type = getattr(msg, 'type', None) if hasattr(msg, 'type') else msg.get('type', '')
                
                # Проверяем сообщения от пользователя
                if msg_type in ['human', 'user']:
                    user_messages_count += 1
            
            # Если есть хотя бы одно предыдущее сообщение от пользователя (user_messages_count > 1),
            # значит это не первое сообщение
            # Учитываем, что текущее сообщение пользователя уже в истории,
            # поэтому если user_messages_count > 1, значит есть предыдущие сообщения
            if user_messages_count > 1:
                # Есть предыдущие сообщения от пользователя - это не первое
                return False
            
            # Если только одно сообщение от пользователя (текущее), значит это первое сообщение
            return True
            
    except Exception as e:
        logger.error(f"Ошибка при проверке первого сообщения: {e}", exc_info=True)
        # В случае ошибки возвращаем False, чтобы не добавлять приветствие
        return False


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
    
    # Приводим текст к нижнему регистру для проверки
    text_lower = text.lower().strip()
    
    # Список приветствий для проверки
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
    
    # Проверяем, начинается ли текст с приветствия
    for greeting in greetings:
        if text_lower.startswith(greeting):
            return True
    
    # Также проверяем, есть ли приветствие в первых 50 символах
    # (на случай, если приветствие не в самом начале)
    text_start = text_lower[:50]
    for greeting in greetings:
        if greeting in text_start:
            return True
    
    return False


async def add_greeting_if_needed(text: str, chat_id: str) -> str:
    """
    Добавляет приветствие "Добрый день" в начало текста, если:
    1. Это первое сообщение пользователя
    2. В тексте еще нет приветствия
    
    Args:
        text: Текст сообщения от агента
        chat_id: ID чата в Telegram
        
    Returns:
        Текст с добавленным приветствием (если нужно) или исходный текст
    """
    if not text or not text.strip():
        return text
    
    try:
        # Проверяем, является ли это первым сообщением
        is_first = await is_first_user_message(chat_id)
        
        if not is_first:
            # Не первое сообщение - не добавляем приветствие
            return text
        
        # Проверяем, есть ли уже приветствие в тексте
        if has_greeting(text):
            # Приветствие уже есть - не добавляем
            logger.debug(f"Приветствие уже присутствует в тексте для chat_id={chat_id}")
            return text
        
        # Добавляем приветствие в начало
        greeting = "Добрый день"
        result = f"{greeting}\n\n{text}"
        logger.info(f"Добавлено приветствие для первого сообщения, chat_id={chat_id}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении приветствия: {e}", exc_info=True)
        # В случае ошибки возвращаем исходный текст
        return text

