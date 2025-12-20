"""
Модуль для работы с LangGraph (OpenAI API)
"""
import os
import time
import asyncio
import json
from datetime import datetime
import pytz
from typing import Optional, List, Dict, Any

from .debug_service import DebugService
from .logger_service import logger
from ..graph.main_graph import MainGraph
from .langgraph_service import LangGraphService
import requests


class AgentService:
    """Сервис для работы с LangGraph (OpenAI API)"""
    
    def __init__(self, debug_service: DebugService):
        """Инициализация сервиса с внедрением зависимостей"""
        self.debug_service = debug_service
        
        # Ленивая инициализация LangGraph
        self._langgraph_service = None
        self._main_graph = None
        
        # Инициализация кэша времени
        self._time_cache = None
        self._time_cache_timestamp = 0
    
    @property
    def langgraph_service(self) -> LangGraphService:
        """Ленивая инициализация LangGraphService"""
        if self._langgraph_service is None:
            self._langgraph_service = LangGraphService()
        return self._langgraph_service
    
    @property
    def main_graph(self) -> MainGraph:
        """Ленивая инициализация MainGraph"""
        if self._main_graph is None:
            self._main_graph = MainGraph(self.langgraph_service)
        return self._main_graph
    
    def _get_moscow_time(self) -> str:
        """Получить текущее время и дату в московском часовом поясе через внешний API"""
        current_time = time.time()
        
        # Используем кэш, если прошло меньше минуты
        if self._time_cache and (current_time - self._time_cache_timestamp) < 60:
            return self._time_cache
        
        try:
            # Получаем точное время через WorldTimeAPI
            response = requests.get(
                'http://worldtimeapi.org/api/timezone/Europe/Moscow',
                timeout=2
            )
            response.raise_for_status()
            data = response.json()
            datetime_str = data['datetime']
            
            # Преобразуем строку в datetime
            if datetime_str.endswith('Z'):
                datetime_str = datetime_str[:-1] + '+00:00'
            moscow_time = datetime.fromisoformat(datetime_str)
            
            # Форматируем
            date_time_str = moscow_time.strftime("%Y-%m-%d %H:%M")
            result = f"Текущее время: {date_time_str}"
            
            # Сохраняем в кэш
            self._time_cache = result
            self._time_cache_timestamp = current_time
            
            return result
        except Exception:
            # Fallback на системное время
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_time = datetime.now(moscow_tz)
            date_time_str = moscow_time.strftime("%Y-%m-%d %H:%M")
            result = f"Текущее время: {date_time_str}"
            
            # Кэшируем fallback тоже
            self._time_cache = result
            self._time_cache_timestamp = current_time
            
            return result
    
    async def send_to_agent_langgraph(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения через LangGraph с использованием PostgreSQL для истории"""
        from ..graph.conversation_state import ConversationState
        from ..storage.conversation_repo import get_conversation_repo
        
        # Получаем telegram_user_id из chat_id (они равны для личных чатов)
        try:
            telegram_user_id = int(chat_id)
        except ValueError:
            logger.error(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id")
            telegram_user_id = 0
        
        # Получаем репозиторий
        conversation_repo = get_conversation_repo()
        
        # Получаем или создаём conversation_id для этого пользователя
        conversation_id = await asyncio.to_thread(
            conversation_repo.get_or_create_conversation,
            telegram_user_id
        )
        
        # Добавляем московское время в начало сообщения
        moscow_time = self._get_moscow_time()
        input_with_time = f"[{moscow_time}] {user_text}"
        
        # Сохраняем входящее сообщение пользователя
        await asyncio.to_thread(
            conversation_repo.append_message,
            conversation_id,
            "user",
            input_with_time
        )
        
        # Загружаем историю последних 30 сообщений (включая только что добавленное)
        history_messages = await asyncio.to_thread(
            conversation_repo.load_last_messages,
            conversation_id,
            limit=30
        )
        
        logger.info(f"Загружено {len(history_messages)} сообщений из истории для conversation_id={conversation_id}")
        
        # Загружаем extracted_info из последнего системного сообщения
        extracted_info = None
        for msg in reversed(history_messages):
            if msg.get("role") == "system" and msg.get("content", "").startswith("EXTRACTED_INFO:"):
                try:
                    extracted_info_json = msg["content"].replace("EXTRACTED_INFO:", "").strip()
                    extracted_info = json.loads(extracted_info_json)
                    logger.debug(f"Загружен extracted_info из истории: {extracted_info}")
                    break
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Ошибка при загрузке extracted_info из истории: {e}")
                    break
        
        # Создаём начальное состояние
        initial_state: ConversationState = {
            "message": input_with_time,
            "chat_id": chat_id,
            "conversation_id": conversation_id,
            "history": history_messages,  # Передаём историю в граф
            "stage": None,
            "extracted_info": extracted_info,
            "answer": "",
            "manager_alert": None
        }
        
        # Выполняем граф
        result_state = await asyncio.to_thread(
            self.main_graph.compiled_graph.invoke,
            initial_state
        )
        
        # Извлекаем ответ
        answer = result_state.get("answer", "")
        manager_alert = result_state.get("manager_alert")
        
        # Сохраняем ответ ассистента в Postgres
        if answer:
            await asyncio.to_thread(
                conversation_repo.append_message,
                conversation_id,
                "assistant",
                answer
            )
        
        # Сохраняем информацию о tool-вызовах, если были
        used_tools = result_state.get("used_tools", [])
        if used_tools:
            tools_info = f"Tools used: {', '.join(used_tools)}"
            await asyncio.to_thread(
                conversation_repo.append_message,
                conversation_id,
                "system",
                tools_info,
                {"tools": used_tools}
            )
        
        # Сохраняем extracted_info в системное сообщение для следующего вызова
        extracted_info = result_state.get("extracted_info")
        if extracted_info:
            try:
                extracted_info_json = json.dumps(extracted_info, ensure_ascii=False)
                await asyncio.to_thread(
                    conversation_repo.append_message,
                    conversation_id,
                    "system",
                    f"EXTRACTED_INFO:{extracted_info_json}"
                )
                logger.debug(f"Сохранен extracted_info в системное сообщение")
            except Exception as e:
                logger.warning(f"Ошибка при сохранении extracted_info: {e}")
        
        # Нормализуем даты и время в ответе
        from .date_normalizer import normalize_dates_in_text
        from .time_normalizer import normalize_times_in_text
        from .link_converter import convert_yclients_links_in_text
        
        answer = normalize_dates_in_text(answer)
        answer = normalize_times_in_text(answer)
        answer = convert_yclients_links_in_text(answer)
        
        result = {"user_message": answer}
        if manager_alert:
            manager_alert = normalize_dates_in_text(manager_alert)
            manager_alert = normalize_times_in_text(manager_alert)
            manager_alert = convert_yclients_links_in_text(manager_alert)
            result["manager_alert"] = manager_alert
        
        return result
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через LangGraph"""
        return await self.send_to_agent_langgraph(chat_id, user_text)
    
    async def reset_context(self, chat_id: str):
        """Сброс контекста для чата"""
        try:
            from ..storage.conversation_repo import get_conversation_repo
            
            # Получаем telegram_user_id из chat_id
            try:
                telegram_user_id = int(chat_id)
            except ValueError:
                logger.error(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id")
                telegram_user_id = 0
            
            # Создаём новый диалог в Postgres (старый останется в базе)
            conversation_repo = get_conversation_repo()
            new_conversation_id = await asyncio.to_thread(
                conversation_repo.create_new_conversation,
                telegram_user_id
            )
            # Логирование создания диалога уже есть в conversation_repo
            
            # Очищаем историю результатов инструментов
            try:
                from .tool_history_service import get_tool_history_service
                tool_history_service = get_tool_history_service()
                tool_history_service.clear_history(chat_id)
                logger.debug(f"История результатов инструментов очищена для chat_id={chat_id}")
            except Exception as e:
                logger.debug(f"Ошибка при очистке истории результатов инструментов: {e}")
            
            # Логирование успеха уже есть в bot.py
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))
