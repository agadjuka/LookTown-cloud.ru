"""
Утилита для retry запросов к API с паузами при ошибке 429
"""
import asyncio
import aiohttp
from typing import Callable, TypeVar, Optional
from ....services.logger_service import logger

T = TypeVar('T')


async def retry_with_backoff(
    operation: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    operation_name: str = "API запрос"
) -> T:
    """
    Выполняет операцию с retry и экспоненциальной задержкой при ошибке 429
    
    Args:
        operation: Асинхронная функция для выполнения
        max_retries: Максимальное количество попыток (включая первую)
        initial_delay: Начальная задержка в секундах
        backoff_factor: Множитель для увеличения задержки
        operation_name: Название операции для логирования
        
    Returns:
        Результат выполнения операции
        
    Raises:
        Последнее исключение, если все попытки исчерпаны
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await operation()
        except aiohttp.ClientResponseError as e:
            last_exception = e
            # Проверяем, является ли это ошибкой 429
            if e.status == 429:
                if attempt < max_retries - 1:
                    delay = initial_delay * (backoff_factor ** attempt)
                    logger.warning(
                        f"{operation_name}: получена ошибка 429 (Too Many Requests) на попытке {attempt + 1}/{max_retries}. "
                        f"Повтор через {delay:.1f} секунд..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"{operation_name}: ошибка 429 после {max_retries} попыток. "
                        f"Все попытки исчерпаны."
                    )
                    raise
            else:
                # Для других HTTP ошибок не делаем retry
                raise
        except Exception as e:
            # Для других исключений проверяем, содержит ли сообщение об ошибке 429
            error_str = str(e).lower()
            if "429" in error_str or "too many requests" in error_str:
                if attempt < max_retries - 1:
                    delay = initial_delay * (backoff_factor ** attempt)
                    logger.warning(
                        f"{operation_name}: обнаружена ошибка 429 в сообщении на попытке {attempt + 1}/{max_retries}. "
                        f"Повтор через {delay:.1f} секунд..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"{operation_name}: ошибка 429 после {max_retries} попыток. "
                        f"Все попытки исчерпаны."
                    )
                    raise
            else:
                # Для других ошибок не делаем retry
                raise
    
    # Если дошли сюда, значит все попытки исчерпаны
    if last_exception:
        raise last_exception
    raise Exception(f"{operation_name}: все попытки исчерпаны без результата")



