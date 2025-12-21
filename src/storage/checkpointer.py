"""Модуль для работы с PostgreSQL Checkpointer для LangGraph"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from ..services.logger_service import logger


def _get_connection_string() -> str:
    """
    Получить строку подключения к PostgreSQL из переменных окружения.
    
    Сначала проверяет DATABASE_URL, если его нет - собирает из отдельных переменных.
    
    Returns:
        Строка подключения в формате postgresql://user:pass@host:port/db
    """
    # Проверяем наличие полной строки подключения
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        logger.info("Используется DATABASE_URL для подключения к PostgreSQL")
        return database_url
    
    # Собираем строку подключения из отдельных переменных
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    database = os.getenv("PG_DB", "ai_db")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    
    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    logger.info(f"Строка подключения собрана из переменных окружения: {host}:{port}/{database}")
    
    return connection_string


@asynccontextmanager
async def get_postgres_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """
    Асинхронный контекстный менеджер для получения AsyncPostgresSaver.
    
    Создает пул соединений, инициализирует checkpointer и вызывает setup()
    для автоматического создания необходимых таблиц в БД.
    
    Yields:
        AsyncPostgresSaver: Экземпляр checkpointer для LangGraph
        
    Raises:
        Exception: При ошибках подключения или инициализации
        
    Example:
        async with get_postgres_checkpointer() as checkpointer:
            # Использование checkpointer
            graph = graph.compile(checkpointer=checkpointer)
    """
    connection_string = _get_connection_string()
    pool: AsyncConnectionPool | None = None
    checkpointer: AsyncPostgresSaver | None = None
    
    try:
        # Создаем пул соединений
        logger.info("Создание пула соединений PostgreSQL для LangGraph Checkpointer...")
        pool = AsyncConnectionPool(conninfo=connection_string, open=False)
        await pool.open()
        logger.info("✅ Пул соединений PostgreSQL успешно создан")
        
        # Инициализируем checkpointer
        logger.info("Инициализация AsyncPostgresSaver...")
        checkpointer = AsyncPostgresSaver(pool)
        
        # ВАЖНО: Вызываем setup() для создания необходимых таблиц
        logger.info("Выполнение setup() для создания таблиц в БД...")
        await checkpointer.setup()
        logger.info("✅ AsyncPostgresSaver успешно инициализирован и готов к работе")
        
        yield checkpointer
        
    except Exception as e:
        logger.error(f"❌ Ошибка при работе с PostgreSQL Checkpointer: {e}")
        logger.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
        raise
    finally:
        # Закрываем пул соединений
        if pool is not None:
            try:
                await pool.close()
                logger.info("Пул соединений PostgreSQL закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии пула соединений: {e}")

