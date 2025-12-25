"""
Единый обработчик технических ошибок для инструментов
"""
import aiohttp
import json
from typing import Optional, Type, Tuple, Any
from functools import wraps

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class SystemError(Exception):
    """Исключение для технических ошибок системы"""
    pass


class APIError(Exception):
    """Исключение для ошибок API с кодом статуса"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


def is_technical_error(exception: Exception) -> bool:
    """
    Определяет, является ли ошибка технической
    
    Технические ошибки:
    - ValueError (конфигурация)
    - aiohttp.ClientError, aiohttp.ClientResponseError
    - ConnectionError, TimeoutError
    - JSONDecodeError
    - APIError (ошибки API с кодом статуса)
    - Exception (любые необработанные исключения)
    
    Бизнес-ошибки (НЕ технические):
    - Слоты не найдены
    - Услуга не найдена
    - Мастер не найден
    - Конфликт при создании записи
    - Клиент не найден
    
    Args:
        exception: Исключение для проверки
        
    Returns:
        True если ошибка техническая, False если бизнес-ошибка
    """
    # Технические ошибки
    if isinstance(exception, (ValueError, ConnectionError, TimeoutError)):
        return True
    
    if isinstance(exception, (aiohttp.ClientError, aiohttp.ClientResponseError)):
        return True
    
    if isinstance(exception, json.JSONDecodeError):
        return True
    
    # Проверяем, является ли это APIError
    if isinstance(exception, APIError):
        return True
    
    # Если это SystemError - точно техническая
    if isinstance(exception, SystemError):
        return True
    
    # Любые другие необработанные исключения считаем техническими
    # Бизнес-ошибки должны обрабатываться в логике и возвращаться как dict с success=False
    return True


def format_system_error(exception: Exception, operation_name: str = "операция") -> str:
    """
    Форматирует техническую ошибку в единое сообщение
    
    Args:
        exception: Исключение
        operation_name: Название операции для контекста
        
    Returns:
        Отформатированное сообщение об ошибке
    """
    error_type = type(exception).__name__
    error_message = str(exception)
    
    # Специальная обработка для разных типов ошибок
    if isinstance(exception, ValueError):
        if "AUTH_HEADER" in error_message or "COMPANY_ID" in error_message or "AuthenticationToken" in error_message or "CompanyID" in error_message:
            return f"System Error: Ошибка конфигурации. {error_message}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
        return f"System Error: Ошибка конфигурации при выполнении {operation_name}. {error_message}"
    
    if isinstance(exception, (aiohttp.ClientError, aiohttp.ClientResponseError)):
        status_code = getattr(exception, 'status', None)
        if status_code:
            return f"System Error: Ошибка при обращении к API (HTTP {status_code}) при выполнении {operation_name}. {error_message}"
        return f"System Error: Ошибка сети при выполнении {operation_name}. {error_message}"
    
    # Проверяем APIError
    if isinstance(exception, APIError):
        status_code = getattr(exception, 'status_code', None)
        if status_code:
            return f"System Error: Ошибка при обращении к API (HTTP {status_code}) при выполнении {operation_name}. {error_message}"
        return f"System Error: Ошибка API при выполнении {operation_name}. {error_message}"
    
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return f"System Error: Ошибка подключения при выполнении {operation_name}. {error_message}"
    
    if isinstance(exception, json.JSONDecodeError):
        return f"System Error: Ошибка парсинга данных при выполнении {operation_name}. {error_message}"
    
    # Общий случай
    return f"System Error: Техническая ошибка при выполнении {operation_name}. {error_type}: {error_message}"


def handle_technical_errors(operation_name: str = "операция"):
    """
    Декоратор для обработки технических ошибок в инструментах
    
    Args:
        operation_name: Название операции для контекста
        
    Usage:
        @handle_technical_errors("создание записи")
        def process(self, thread: Thread) -> str:
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Логируем ошибку
                logger.error(f"Техническая ошибка в {operation_name}: {e}", exc_info=True)
                
                # Проверяем, является ли это технической ошибкой
                if is_technical_error(e):
                    return format_system_error(e, operation_name)
                else:
                    # Если это не техническая ошибка, пробрасываем дальше
                    raise
        
        return wrapper
    return decorator


def wrap_tool_process(operation_name: str):
    """
    Обертка для метода process инструментов
    
    Args:
        operation_name: Название операции
        
    Returns:
        Обернутая функция
    """
    def decorator(process_func):
        @wraps(process_func)
        def wrapper(self, thread, *args, **kwargs):
            try:
                return process_func(self, thread, *args, **kwargs)
            except Exception as e:
                # Логируем ошибку
                logger.error(f"Техническая ошибка в {operation_name}: {e}", exc_info=True)
                
                # Проверяем, является ли это технической ошибкой
                if is_technical_error(e):
                    return format_system_error(e, operation_name)
                else:
                    # Если это не техническая ошибка, пробрасываем дальше
                    raise
        
        return wrapper
    return decorator

