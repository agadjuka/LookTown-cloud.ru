"""
Сервис для транскрибации аудио через Yandex SpeechKit STT API
"""
import os
import requests
from typing import Literal, Optional
from src.services.logger_service import logger
from src.services.auth_service import AuthService


class SpeechTooLongError(Exception):
    """Исключение для слишком длинных аудио файлов"""
    pass


class SpeechKitSTTService:
    """Сервис для работы с Yandex SpeechKit STT API"""
    
    STT_ENDPOINT = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ в байтах
    MAX_DURATION_SECONDS = 30  # 30 секунд
    
    def __init__(self, auth_service: Optional[AuthService] = None):
        """
        Инициализация сервиса транскрибации
        
        Args:
            auth_service: Сервис аутентификации (опционально, создается автоматически)
        """
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YC_SPEECHKIT_API_KEY") or os.getenv("YANDEX_API_KEY_SECRET")
        
        if not self.folder_id:
            raise ValueError("Не задан YANDEX_FOLDER_ID в переменных окружения")
        
        if not self.api_key:
            # Если нет API ключа, используем IAM токен через AuthService
            self.auth_service = auth_service or AuthService()
            self.use_iam_token = True
        else:
            self.auth_service = None
            self.use_iam_token = False
    
    def _get_authorization_header(self) -> str:
        """Получить заголовок авторизации"""
        if self.use_iam_token:
            iam_token = self.auth_service.get_iam_token()
            return f"Bearer {iam_token}"
        else:
            return f"Api-Key {self.api_key}"
    
    def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        source: Literal["telegram", "whatsapp"] = "telegram",
        lang: str = "ru-RU"
    ) -> str:
        """
        Транскрибировать аудио в текст
        
        Args:
            audio_bytes: Сырое содержимое аудио файла в байтах
            mime_type: MIME тип файла (audio/ogg, audio/opus, audio/mpeg и т.п.)
            source: Источник аудио (для логирования)
            lang: Язык распознавания (по умолчанию ru-RU)
        
        Returns:
            Распознанный текст
        
        Raises:
            SpeechTooLongError: Если файл слишком большой
            Exception: При ошибках API
        """
        # Проверка размера файла
        file_size = len(audio_bytes)
        logger.info(f"Начало транскрибации аудио из {source}. Размер: {file_size} байт, MIME: {mime_type}")
        
        if file_size > self.MAX_FILE_SIZE:
            error_msg = f"Аудио файл слишком большой: {file_size} байт (максимум {self.MAX_FILE_SIZE} байт)"
            logger.warning(error_msg)
            raise SpeechTooLongError(error_msg)
        
        # Подготовка запроса
        headers = {
            "Authorization": self._get_authorization_header(),
            "Content-Type": "application/octet-stream"
        }
        
        # Определяем формат для SpeechKit
        # SpeechKit поддерживает: lpcm, oggopus, mp3
        format_param = self._get_format_from_mime(mime_type)
        
        params = {
            "lang": lang,
            "folderId": self.folder_id,
            "format": format_param
        }
        
        try:
            # Отправка запроса
            logger.info(f"Отправка запроса в SpeechKit STT. Формат: {format_param}, язык: {lang}")
            response = requests.post(
                self.STT_ENDPOINT,
                headers=headers,
                params=params,
                data=audio_bytes,
                timeout=30
            )
            
            # Обработка ответа
            response.raise_for_status()
            result = response.json()
            
            # Проверка на ошибки в ответе
            if "error_code" in result or "error_message" in result:
                error_code = result.get("error_code", "unknown")
                error_message = result.get("error_message", "Unknown error")
                error_msg = f"SpeechKit STT вернул ошибку: {error_code} - {error_message}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # Извлечение текста
            transcribed_text = result.get("result", "")
            
            if not transcribed_text:
                logger.warning("SpeechKit STT вернул пустой результат")
                return ""
            
            logger.info(f"Транскрибация успешна. Длина текста: {len(transcribed_text)} символов")
            return transcribed_text.strip()
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка при запросе к SpeechKit STT: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Неожиданная ошибка при транскрибации: {str(e)}", exc_info=True)
            raise
    
    def _get_format_from_mime(self, mime_type: str) -> str:
        """
        Преобразовать MIME тип в формат для SpeechKit
        
        Args:
            mime_type: MIME тип (audio/ogg, audio/opus, audio/mpeg и т.п.)
        
        Returns:
            Формат для SpeechKit (lpcm, oggopus, mp3)
        """
        mime_lower = mime_type.lower()
        
        if "ogg" in mime_lower or "opus" in mime_lower:
            return "oggopus"
        elif "mp3" in mime_lower or "mpeg" in mime_lower:
            return "mp3"
        elif "lpcm" in mime_lower or "pcm" in mime_lower:
            return "lpcm"
        else:
            # По умолчанию для Telegram голосовых сообщений - oggopus
            logger.warning(f"Неизвестный MIME тип {mime_type}, используем oggopus по умолчанию")
            return "oggopus"


# Singleton экземпляр
_speechkit_stt_service: Optional[SpeechKitSTTService] = None


def get_speechkit_stt_service(auth_service: Optional[AuthService] = None) -> SpeechKitSTTService:
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

