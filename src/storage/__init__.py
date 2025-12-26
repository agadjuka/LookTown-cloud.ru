"""Модуль для работы с хранилищем данных."""

from src.storage.topic_storage import BaseTopicStorage
from src.storage.topic_storage_factory import get_topic_storage
from src.storage.postgres_topic_storage import PostgresTopicStorage

__all__ = [
    "BaseTopicStorage",
    "get_topic_storage",
    "PostgresTopicStorage",
]


