"""
Утилиты для обработки голосовых сообщений
"""
from telegram import Update
from typing import Optional, Tuple
from src.services.logger_service import logger
from src.services.speechkit_stt import get_speechkit_stt_service, SpeechTooLongError


async def download_voice_to_memory(bot, file_id: str) -> bytes:
    """
    Скачать голосовое сообщение в память
    
    Args:
        bot: Экземпляр бота
        file_id: ID файла в Telegram
    
    Returns:
        Байты аудио файла
    """
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
    """
    Транскрибировать голосовое сообщение
    
    Args:
        bot: Экземпляр бота
        voice_file_id: ID голосового файла в Telegram
        chat_id: ID чата для логирования
    
    Returns:
        Tuple[transcribed_text, error_message]
        - Если успешно: (transcribed_text, None)
        - Если ошибка: (None, error_message)
    """
    try:
        # Скачиваем аудио в память
        audio_bytes = await download_voice_to_memory(bot, voice_file_id)
        
        # Получаем MIME тип (Telegram обычно использует audio/ogg для голосовых)
        mime_type = "audio/ogg"  # Telegram голосовые сообщения в формате OGG
        
        # Транскрибируем через SpeechKit STT
        try:
            stt_service = get_speechkit_stt_service()
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
            return None, (
                "Голосовое сообщение слишком длинное (максимум 30 секунд или 1 МБ). "
                "Попробуйте отправить более короткое сообщение или текстовое сообщение."
            )
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
    """
    Извлечь текст из сообщения (текстового или голосового)
    
    Args:
        update: Telegram Update объект
        bot: Экземпляр бота
        chat_id: ID чата для логирования
    
    Returns:
        Tuple[message_text, error_message, is_voice]
        - Если текстовое: (text, None, False)
        - Если голосовое успешно: (transcribed_text, None, True)
        - Если ошибка: (None, error_message, True)
    """
    if update.message.voice:
        # Голосовое сообщение
        logger.telegram("Получено голосовое сообщение", chat_id)
        transcribed_text, error_message = await transcribe_voice_message(
            bot=bot,
            voice_file_id=update.message.voice.file_id,
            chat_id=chat_id
        )
        return transcribed_text, error_message, True
    else:
        # Текстовое сообщение
        logger.telegram("Получено сообщение", chat_id)
        return update.message.text, None, False
