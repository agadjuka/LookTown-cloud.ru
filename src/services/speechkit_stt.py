"""
Сервис для транскрибации аудио через Yandex SpeechKit STT API
"""
import os
import requests
from typing import Literal, Optional, Any
from src.services.logger_service import logger


class SpeechTooLongError(Exception):
    """Исключение для слишком длинных аудио файлов"""
    pass


class SpeechKitSTTService:
    """
    Заглушка для сервиса STT (Yandex SpeechKit отключен)
    """
    
    def __init__(self, auth_service: Optional[Any] = None):
        pass
    
    def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        source: str = "telegram",
        lang: str = "ru-RU"
    ) -> str:
        """
        Транскрибировать аудио в текст (отключено)
        """
        logger.warning("Попытка использования STT, но сервис отключен (Yandex SpeechKit удален)")
        # Возвращаем пустую строку или None, чтобы вызывающий код обработал это
        # В voice_utils.py если вернется None, будет отправлено сообщение об ошибке
        return "" 


# Singleton экземпляр
_speechkit_stt_service: Optional[SpeechKitSTTService] = None


def get_speechkit_stt_service(auth_service: Optional[Any] = None) -> SpeechKitSTTService:
    """
    Получить singleton экземпляр SpeechKitSTTService
    
    Args:
        auth_service: Сервис аутентификации (опционально)
    
    Returns:
        Экземпляр SpeechKitSTTService
    """
    global _speechkit_stt_service
    if _speechkit_stt_service is None:
        _speechkit_stt_service = SpeechKitSTTService(auth_service=auth_service)
    return _speechkit_stt_service

