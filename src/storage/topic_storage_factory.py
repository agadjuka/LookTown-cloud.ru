"""Фабрика для создания экземпляра хранилища топиков."""

import logging
from typing import Optional

from src.storage.topic_storage import BaseTopicStorage

logger = logging.getLogger(__name__)

# Глобальный экземпляр хранилища
_topic_storage: Optional[BaseTopicStorage] = None


def get_topic_storage() -> Optional[BaseTopicStorage]:
    """
    Получает или создает экземпляр хранилища топиков.
    
    Returns:
        Экземпляр хранилища топиков или None, если хранилище не настроено
    """
    global _topic_storage
    
    if _topic_storage is None:
        logger.warning("Хранилище топиков (TopicStorage) не настроено. Админ-панель может не работать.")
        # Здесь можно будет добавить инициализацию PostgresTopicStorage в будущем
        pass
    
    return _topic_storage
