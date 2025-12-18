# Инструкция по интеграции модуля обработки голосовых сообщений

## Требования

- `python-telegram-bot` >= 21.0
- `requests`
- Yandex Cloud аккаунт с папкой (folder)
- SpeechKit STT активирован
- Сервисный аккаунт с ролью `ai.speechkit-stt.user` или API-ключ

## Переменные окружения

```bash
# Обязательно
YANDEX_FOLDER_ID=your_folder_id

# Опционально (выберите один вариант)
YC_SPEECHKIT_API_KEY=your_api_key
# ИЛИ
YANDEX_API_KEY_SECRET=your_api_key
# Если не указано - будет использован IAM токен через AuthService
```

## Шаг 1: Создать сервис транскрибации

Создайте файл `src/services/speechkit_stt.py`:

```python
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
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 МБ
    
    def __init__(self, auth_service: Optional[AuthService] = None):
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        self.api_key = os.getenv("YC_SPEECHKIT_API_KEY") or os.getenv("YANDEX_API_KEY_SECRET")
        
        if not self.folder_id:
            raise ValueError("Не задан YANDEX_FOLDER_ID в переменных окружения")
        
        if not self.api_key:
            self.auth_service = auth_service or AuthService()
            self.use_iam_token = True
        else:
            self.auth_service = None
            self.use_iam_token = False
    
    def _get_authorization_header(self) -> str:
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
        file_size = len(audio_bytes)
        logger.info(f"Начало транскрибации аудио из {source}. Размер: {file_size} байт")
        
        if file_size > self.MAX_FILE_SIZE:
            raise SpeechTooLongError(f"Аудио файл слишком большой: {file_size} байт")
        
        headers = {
            "Authorization": self._get_authorization_header(),
            "Content-Type": "application/octet-stream"
        }
        
        format_param = "oggopus" if "ogg" in mime_type.lower() or "opus" in mime_type.lower() else "mp3"
        
        params = {
            "lang": lang,
            "folderId": self.folder_id,
            "format": format_param
        }
        
        response = requests.post(
            self.STT_ENDPOINT,
            headers=headers,
            params=params,
            data=audio_bytes,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        if "error_code" in result or "error_message" in result:
            error_code = result.get("error_code", "unknown")
            error_message = result.get("error_message", "Unknown error")
            raise Exception(f"SpeechKit STT вернул ошибку: {error_code} - {error_message}")
        
        transcribed_text = result.get("result", "")
        return transcribed_text.strip() if transcribed_text else ""


_speechkit_stt_service: Optional[SpeechKitSTTService] = None


def get_speechkit_stt_service(auth_service: Optional[AuthService] = None) -> SpeechKitSTTService:
    global _speechkit_stt_service
    if _speechkit_stt_service is None:
        _speechkit_stt_service = SpeechKitSTTService(auth_service=auth_service)
    return _speechkit_stt_service
```

## Шаг 2: Создать утилиты для голосовых сообщений

Создайте файл `src/handlers/voice_utils.py`:

```python
"""
Утилиты для обработки голосовых сообщений
"""
from telegram import Update
from typing import Optional, Tuple
from src.services.logger_service import logger
from src.services.speechkit_stt import get_speechkit_stt_service, SpeechTooLongError
from src.services.auth_service import AuthService


async def download_voice_to_memory(bot, file_id: str) -> bytes:
    logger.info(f"Начало скачивания голосового сообщения. File ID: {file_id}")
    file = await bot.get_file(file_id)
    audio_bytearray = await file.download_as_bytearray()
    audio_bytes = bytes(audio_bytearray)
    logger.info(f"Голосовое сообщение скачано. Размер: {len(audio_bytes)} байт")
    return audio_bytes


async def transcribe_voice_message(
    bot,
    voice_file_id: str,
    chat_id: str
) -> Tuple[Optional[str], Optional[str]]:
    try:
        audio_bytes = await download_voice_to_memory(bot, voice_file_id)
        mime_type = "audio/ogg"
        
        try:
            auth_service = AuthService()
            stt_service = get_speechkit_stt_service(auth_service=auth_service)
            transcribed_text = stt_service.transcribe(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                source="telegram"
            )
            
            if not transcribed_text:
                logger.warning("Транскрибация вернула пустой текст", chat_id)
                return None, "Не удалось распознать речь в аудиосообщении. Попробуйте отправить текстовое сообщение."
            
            logger.info(f"Транскрибация успешна. Текст: {transcribed_text[:100]}...", chat_id)
            return transcribed_text, None
            
        except SpeechTooLongError as e:
            logger.warning(f"Голосовое сообщение слишком длинное: {str(e)}", chat_id)
            return None, "Голосовое сообщение слишком длинное (максимум 30 секунд или 1 МБ). Попробуйте отправить более короткое сообщение."
        except Exception as e:
            logger.error(f"Ошибка при транскрибации аудио: {str(e)}", chat_id, exc_info=True)
            return None, "Произошла ошибка при обработке аудиосообщения. Попробуйте отправить текстовое сообщение."
            
    except Exception as e:
        logger.error(f"Ошибка при скачивании голосового сообщения: {str(e)}", chat_id, exc_info=True)
        return None, "Произошла ошибка при скачивании аудиосообщения. Попробуйте отправить текстовое сообщение."


async def extract_message_text(
    update: Update,
    bot,
    chat_id: str
) -> Tuple[Optional[str], Optional[str], bool]:
    if update.message.voice:
        logger.telegram("Получено голосовое сообщение", chat_id)
        transcribed_text, error_message = await transcribe_voice_message(
            bot=bot,
            voice_file_id=update.message.voice.file_id,
            chat_id=chat_id
        )
        return transcribed_text, error_message, True
    else:
        logger.telegram("Получено сообщение", chat_id)
        return update.message.text, None, False
```

## Шаг 3: Обновить обработчик сообщений

В вашем обработчике (`src/handlers/telegram_handlers.py` или `bot.py`) измените функцию `handle_message()`:

**До:**
```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    # ... остальной код
```

**После:**
```python
from src.handlers.voice_utils import extract_message_text

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    
    # Извлекаем текст из сообщения (текстового или голосового)
    user_message, error_message, is_voice = await extract_message_text(
        update=update,
        bot=context.bot,
        chat_id=chat_id
    )
    
    # Если была ошибка при обработке голосового сообщения
    if error_message:
        await update.message.reply_text(error_message)
        return
    
    # Проверка, что у нас есть текст для обработки
    if not user_message:
        logger.warning("Получено сообщение без текста", chat_id)
        return
    
    # ... остальной код обработки (отправка в агента и т.д.)
```

## Шаг 4: Обновить фильтр обработчика

Измените регистрацию обработчика:

**До:**
```python
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
```

**После:**
```python
application.add_handler(MessageHandler((filters.TEXT | filters.VOICE) & ~filters.COMMAND, handle_message))
```

## Шаг 5: Обновить экспорты (опционально)

В `src/services/__init__.py` добавьте:

```python
from .speechkit_stt import SpeechKitSTTService, get_speechkit_stt_service

__all__ = [..., 'SpeechKitSTTService', 'get_speechkit_stt_service']
```

## Готово!

После выполнения этих шагов бот будет автоматически транскрибировать голосовые сообщения и обрабатывать их как обычные текстовые сообщения.

## Ограничения

- Максимальный размер файла: 1 МБ
- Максимальная длительность: 30 секунд
- Поддерживаемые форматы: OGG Opus (Telegram), MP3
