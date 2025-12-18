"""Модуль для работы с PostgreSQL"""
import os
import psycopg2
from psycopg2 import pool
from typing import Optional
from ..services.logger_service import logger


class PostgreSQLClient:
    """Клиент для работы с PostgreSQL"""
    
    def __init__(self):
        """Инициализация подключения к PostgreSQL"""
        # Получаем параметры подключения из переменных окружения
        self.host = os.getenv("PG_HOST", "localhost")
        self.port = os.getenv("PG_PORT", "5432")
        self.database = os.getenv("PG_DB", "ai_db")
        self.user = os.getenv("PG_USER", "postgres")
        self.password = os.getenv("PG_PASSWORD", "")
        
        # Альтернатива: использовать DATABASE_URL
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            self.connection_string = database_url
        else:
            self.connection_string = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        # Создаём пул соединений
        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.connection_string
            )
            logger.info(f"✅ Подключение к PostgreSQL успешно: {self.host}:{self.port}/{self.database}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise
    
    def get_connection(self):
        """Получить соединение из пула"""
        return self.connection_pool.getconn()
    
    def put_connection(self, conn):
        """Вернуть соединение в пул"""
        self.connection_pool.putconn(conn)
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = False):
        """
        Выполнить запрос к базе данных
        
        Args:
            query: SQL запрос
            params: Параметры запроса
            fetch: Нужно ли возвращать результаты (для SELECT)
            
        Returns:
            Результаты запроса (если fetch=True) или None
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                
                if fetch:
                    result = cursor.fetchall()
                    conn.commit()
                    return result
                else:
                    conn.commit()
                    return None
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Ошибка выполнения запроса: {e}")
            logger.error(f"Запрос: {query}")
            logger.error(f"Параметры: {params}")
            raise
        finally:
            if conn:
                self.put_connection(conn)
    
    def execute_query_one(self, query: str, params: tuple = None):
        """
        Выполнить запрос и вернуть одну строку
        
        Args:
            query: SQL запрос
            params: Параметры запроса
            
        Returns:
            Одна строка результата или None
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                result = cursor.fetchone()
                conn.commit()
                return result
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Ошибка выполнения запроса: {e}")
            raise
        finally:
            if conn:
                self.put_connection(conn)
    
    def close(self):
        """Закрыть все соединения в пуле"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connection pool closed")


# Глобальный экземпляр клиента
_pg_client: Optional[PostgreSQLClient] = None


def get_pg_client() -> PostgreSQLClient:
    """Получение глобального экземпляра PostgreSQL клиента"""
    global _pg_client
    if _pg_client is None:
        _pg_client = PostgreSQLClient()
    return _pg_client
