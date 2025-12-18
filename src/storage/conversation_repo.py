"""Репозиторий для работы с диалогами и сообщениями в PostgreSQL"""
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from .pg_client import get_pg_client
from ..services.logger_service import logger


class ConversationRepository:
    """Репозиторий для работы с диалогами и сообщениями"""
    
    def __init__(self):
        """Инициализация репозитория"""
        self.pg_client = get_pg_client()
    
    def get_or_create_conversation(self, telegram_user_id: int) -> str:
        """
        Получить или создать диалог для пользователя Telegram
        
        Args:
            telegram_user_id: ID пользователя в Telegram
            
        Returns:
            UUID диалога (conversation_id)
        """
        # Сначала пытаемся найти существующий диалог
        query = """
            SELECT id 
            FROM public.conversations 
            WHERE telegram_user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        
        result = self.pg_client.execute_query_one(query, (telegram_user_id,))
        
        if result:
            conversation_id = str(result[0])
            logger.debug(f"Найден существующий conversation_id={conversation_id} для telegram_user_id={telegram_user_id}")
            return conversation_id
        
        # Если не найден, создаём новый
        conversation_id = str(uuid.uuid4())
        insert_query = """
            INSERT INTO public.conversations (id, telegram_user_id, created_at)
            VALUES (%s, %s, NOW())
        """
        
        self.pg_client.execute_query(insert_query, (conversation_id, telegram_user_id))
        logger.info(f"✅ Создан новый conversation_id={conversation_id} для telegram_user_id={telegram_user_id}")
        
        return conversation_id
    
    def append_message(
        self, 
        conversation_id: str, 
        role: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Добавить сообщение в диалог
        
        Args:
            conversation_id: UUID диалога
            role: Роль отправителя ('user', 'assistant', 'tool', 'system')
            content: Содержимое сообщения
            metadata: Дополнительные метаданные (опционально)
            
        Returns:
            ID созданного сообщения
        """
        # Валидация роли
        valid_roles = ['user', 'assistant', 'tool', 'system']
        if role not in valid_roles:
            raise ValueError(f"Недопустимая роль: {role}. Допустимые роли: {valid_roles}")
        
        query = """
            INSERT INTO public.messages (conversation_id, role, content, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING id
        """
        
        # metadata не используется (колонка отсутствует в БД)
        
        result = self.pg_client.execute_query_one(
            query, 
            (conversation_id, role, content)
        )
        
        message_id = result[0] if result else None
        logger.debug(f"Сообщение добавлено: message_id={message_id}, role={role}, conversation_id={conversation_id}")
        
        return message_id
    
    def load_last_messages(
        self, 
        conversation_id: str, 
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Загрузить последние N сообщений из диалога
        
        Args:
            conversation_id: UUID диалога
            limit: Количество последних сообщений (по умолчанию 30)
            
        Returns:
            Список сообщений в формате [{"role": "user", "content": "..."}]
        """
        # Берём последние N сообщений и сортируем по возрастанию (хронологический порядок)
        query = """
            SELECT id, role, content, created_at
            FROM (
                SELECT id, role, content, created_at
                FROM public.messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            ) AS recent_messages
            ORDER BY created_at ASC, id ASC
        """
        
        results = self.pg_client.execute_query(query, (conversation_id, limit), fetch=True)
        
        messages = []
        for row in results:
            message = {
                "role": row[1],
                "content": row[2],
            }
            
            messages.append(message)
        
        logger.debug(f"Загружено {len(messages)} сообщений для conversation_id={conversation_id}")
        
        return messages
    
    def create_new_conversation(self, telegram_user_id: int) -> str:
        """
        Создать новый диалог для пользователя (для команды /new)
        
        Старый диалог можно архивировать или удалить (сейчас просто создаём новый)
        
        Args:
            telegram_user_id: ID пользователя в Telegram
            
        Returns:
            UUID нового диалога
        """
        # Создаём новый conversation_id
        new_conversation_id = str(uuid.uuid4())
        
        insert_query = """
            INSERT INTO public.conversations (id, telegram_user_id, created_at)
            VALUES (%s, %s, NOW())
        """
        
        self.pg_client.execute_query(insert_query, (new_conversation_id, telegram_user_id))
        logger.info(f"✅ Создан новый диалог conversation_id={new_conversation_id} для telegram_user_id={telegram_user_id}")
        
        return new_conversation_id
    
    def clear_conversation_messages(self, conversation_id: str):
        """
        Удалить все сообщения из диалога (альтернатива созданию нового)
        
        Args:
            conversation_id: UUID диалога
        """
        query = """
            DELETE FROM public.messages
            WHERE conversation_id = %s
        """
        
        self.pg_client.execute_query(query, (conversation_id,))
        logger.info(f"Все сообщения удалены для conversation_id={conversation_id}")
    
    def get_conversation_by_telegram_user(self, telegram_user_id: int) -> Optional[str]:
        """
        Получить текущий активный диалог пользователя
        
        Args:
            telegram_user_id: ID пользователя в Telegram
            
        Returns:
            UUID диалога или None
        """
        query = """
            SELECT id 
            FROM public.conversations 
            WHERE telegram_user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        
        result = self.pg_client.execute_query_one(query, (telegram_user_id,))
        
        return str(result[0]) if result else None


# Глобальный экземпляр репозитория
_conversation_repo: Optional[ConversationRepository] = None


def get_conversation_repo() -> ConversationRepository:
    """Получение глобального экземпляра репозитория"""
    global _conversation_repo
    if _conversation_repo is None:
        _conversation_repo = ConversationRepository()
    return _conversation_repo
