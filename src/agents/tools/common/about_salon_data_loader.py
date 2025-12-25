"""
Сервис для чтения данных о салоне из облачного хранилища Cloud.ru
"""
import os
from typing import Dict
from functools import lru_cache

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .cloud_ru_storage import load_json_from_cloud_ru


class AboutSalonDataLoader:
    """Загрузчик данных о салоне из Cloud.ru Object Storage"""
    
    def __init__(self):
        """Инициализация загрузчика"""
        pass
    
    @lru_cache(maxsize=1)
    def load_data(self) -> Dict:
        """
        Загрузка данных о салоне из Cloud.ru Object Storage
        
        Returns:
            Словарь с данными о салоне
            
        Raises:
            ValueError: если не заданы необходимые переменные окружения
            ImportError: если не установлен boto3
            Exception: если произошла ошибка при загрузке файла
            json.JSONDecodeError: если ошибка парсинга JSON
        """
        storage_bucket = os.getenv('CLOUD_RU_BUCKET_NAME')
        storage_path = os.getenv('ABOUT_SALON_STORAGE_PATH', 'about_salon.json')
        
        if not storage_bucket:
            raise ValueError("Не задан CLOUD_RU_BUCKET_NAME")
        
        return load_json_from_cloud_ru(storage_bucket, storage_path)
    
    def reload(self):
        """Принудительная перезагрузка данных (очистка кэша)"""
        self.load_data.cache_clear()


# Глобальный экземпляр загрузчика
_about_salon_data_loader = AboutSalonDataLoader()

