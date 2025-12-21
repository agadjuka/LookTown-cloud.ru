"""Модуль для работы с PostgreSQL Checkpointer для LangGraph"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from ..services.logger_service import logger

# Флаг для отслеживания, был ли выполнен setup
_setup_completed = False


async def initialize_checkpointer_tables():
    """
    Инициализирует таблицы для checkpointer один раз при старте приложения.
    Должна быть вызвана один раз при запуске приложения, вне транзакций.
    
    Эта функция создает таблицы и индексы для LangGraph Checkpointer.
    """
    global _setup_completed
    
    if _setup_completed:
        logger.debug("Таблицы checkpointer уже инициализированы")
        return
    
    connection_string = _get_connection_string()
    pool: AsyncConnectionPool | None = None
    
    try:
        logger.info("Инициализация таблиц для LangGraph Checkpointer...")
        print("🔧 Инициализация таблиц для LangGraph Checkpointer...", flush=True)
        
        # Создаем временный пул соединений для инициализации
        pool = AsyncConnectionPool(conninfo=connection_string, open=False)
        await pool.open()
        
        # Создаем экземпляр checkpointer
        checkpointer = AsyncPostgresSaver(pool)
        
        # Вызываем setup() для создания таблиц
        await checkpointer.setup()
        
        _setup_completed = True
        logger.info("✅ Таблицы и индексы для LangGraph Checkpointer успешно созданы")
        print("✅ Таблицы для LangGraph Checkpointer успешно созданы", flush=True)
        
    except Exception as e:
        error_str = str(e)
        
        # Игнорируем ошибки, если таблицы уже существуют
        if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
            logger.info("Таблицы уже существуют, инициализация не требуется")
            print("ℹ️ Таблицы уже существуют, инициализация не требуется", flush=True)
            _setup_completed = True
        elif "CONCURRENTLY" in error_str and "transaction" in error_str.lower():
            # Ошибка CONCURRENTLY - это известная проблема, но таблицы могут быть созданы частично
            logger.warning(f"⚠️ Предупреждение при инициализации (CONCURRENTLY): {e}")
            logger.warning("Таблицы могут быть созданы частично. Проверьте вручную.")
            print(f"⚠️ Предупреждение: {e}", flush=True)
            # Устанавливаем флаг, чтобы не блокировать работу
            _setup_completed = True
        else:
            logger.error(f"Ошибка при инициализации таблиц checkpointer: {e}")
            print(f"❌ Ошибка при инициализации таблиц: {e}", flush=True)
            raise
    finally:
        # Закрываем пул соединений
        if pool is not None:
            try:
                await pool.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии пула при инициализации: {e}")


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
    
    Создает пул соединений, инициализирует checkpointer и гарантирует создание таблиц
    через вызов setup() (идемпотентная операция).
    
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
        
        # ГАРАНТИРУЕМ СОЗДАНИЕ ТАБЛИЦ: setup() является идемпотентным
        # (выполняет CREATE TABLE IF NOT EXISTS), безопасно вызывать каждый раз
        setup_success = False
        try:
            await checkpointer.setup()
            setup_success = True
            logger.info("✅ Таблицы для LangGraph Checkpointer проверены/созданы")
        except Exception as setup_error:
            error_str = str(setup_error)
            # Игнорируем ошибки, если таблицы уже существуют
            if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
                logger.debug("Таблицы уже существуют")
                setup_success = True
            elif "CONCURRENTLY" in error_str and "transaction" in error_str.lower():
                # Ошибка CONCURRENTLY - проверяем, созданы ли таблицы
                logger.warning("⚠️ Ошибка CONCURRENTLY при setup(), проверяем существование таблиц...")
                import psycopg
                try:
                    async with await psycopg.AsyncConnection.connect(connection_string) as check_conn:
                        async with check_conn.cursor() as cur:
                            await cur.execute("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_schema = 'public' 
                                    AND table_name = 'checkpoints'
                                );
                            """)
                            result = await cur.fetchone()
                            if result and result[0]:
                                logger.info("✅ Таблица checkpoints существует, продолжаем работу")
                                setup_success = True
                            else:
                                logger.error("❌ Таблица checkpoints НЕ существует после setup() с ошибкой CONCURRENTLY")
                                raise RuntimeError(
                                    "Таблицы для LangGraph Checkpointer не могут быть созданы автоматически "
                                    "из-за CONCURRENTLY в транзакции. Создайте таблицы вручную через SQL."
                                ) from setup_error
                except RuntimeError:
                    raise
                except Exception as check_error:
                    logger.error(f"❌ Ошибка при проверке существования таблиц: {check_error}")
                    raise RuntimeError(
                        "Не удалось проверить существование таблиц после setup(). "
                        "Убедитесь, что таблицы для LangGraph Checkpointer созданы."
                    ) from check_error
            else:
                # Для других ошибок - проверяем, существуют ли таблицы
                logger.warning(f"⚠️ Ошибка при setup(): {setup_error}")
                logger.warning("Проверяем, существуют ли таблицы...")
                import psycopg
                try:
                    async with await psycopg.AsyncConnection.connect(connection_string) as check_conn:
                        async with check_conn.cursor() as cur:
                            await cur.execute("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_schema = 'public' 
                                    AND table_name = 'checkpoints'
                                );
                            """)
                            result = await cur.fetchone()
                            if result and result[0]:
                                logger.info("✅ Таблица checkpoints существует, продолжаем работу")
                                setup_success = True
                            else:
                                logger.error(f"❌ Таблица checkpoints НЕ существует после ошибки setup(): {setup_error}")
                                raise RuntimeError(
                                    f"Таблицы для LangGraph Checkpointer не могут быть созданы. "
                                    f"Ошибка: {setup_error}"
                                ) from setup_error
                except RuntimeError:
                    raise
                except Exception as check_error:
                    logger.error(f"❌ Ошибка при проверке существования таблиц: {check_error}")
                    raise RuntimeError(
                        f"Не удалось проверить существование таблиц после setup(). "
                        f"Ошибка setup(): {setup_error}"
                    ) from check_error
        
        # Финальная проверка: если setup() не выполнился успешно, проверяем таблицы
        if not setup_success:
            logger.error("❌ setup() не выполнился успешно, но таблицы не были проверены")
            raise RuntimeError(
                "Не удалось гарантировать существование таблиц для LangGraph Checkpointer. "
                "Проверьте логи для деталей."
            )
        
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

