"""
Модуль для работы с LangGraph (OpenAI API)
"""
import time
from datetime import datetime
import pytz

from langchain_core.messages import HumanMessage
from .debug_service import DebugService
from .logger_service import logger
from ..graph.main_graph import create_main_graph
from .langgraph_service import LangGraphService
from ..storage.checkpointer import get_postgres_checkpointer, clear_thread_memory
import requests


class AgentService:
    """Сервис для работы с LangGraph (OpenAI API)"""
    
    def __init__(self, debug_service: DebugService):
        """Инициализация сервиса с внедрением зависимостей"""
        self.debug_service = debug_service
        
        # Ленивая инициализация LangGraph
        self._langgraph_service = None
        
        # Инициализация кэша времени
        self._time_cache = None
        self._time_cache_timestamp = 0
    
    @property
    def langgraph_service(self) -> LangGraphService:
        """Ленивая инициализация LangGraphService"""
        if self._langgraph_service is None:
            self._langgraph_service = LangGraphService()
        return self._langgraph_service
    
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
        """
        Отправка сообщения через LangGraph с использованием нативной памяти PostgreSQL
        
        Граф сам управляет историей через checkpointer, нам нужно только передать новое сообщение.
        """
        # Получаем telegram_user_id из chat_id (они равны для личных чатов)
        try:
            telegram_user_id = int(chat_id)
        except ValueError:
            logger.error(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id")
            telegram_user_id = 0
        
        # Добавляем московское время в начало сообщения
        moscow_time = self._get_moscow_time()
        user_message_text = f"[{moscow_time}] {user_text}"
        
        logger.info(f"Обработка сообщения от chat_id={chat_id}, telegram_user_id={telegram_user_id}")
        
        try:
            # Используем checkpointer для работы с нативной памятью LangGraph
            async with get_postgres_checkpointer() as checkpointer:
                # Создаем граф с checkpointer
                app = create_main_graph(self.langgraph_service, checkpointer=checkpointer)
                
                # Используем ID пользователя как thread_id для изоляции сессий
                config = {"configurable": {"thread_id": str(telegram_user_id)}}
                
                # Формируем входные данные - ТОЛЬКО новое сообщение
                # История граф подтянет сам из БД через checkpointer!
                input_data = {
                    "messages": [HumanMessage(content=user_message_text)],
                    "message": user_message_text,  # Для обратной совместимости с узлами
                    "chat_id": chat_id,
                    "stage": None,
                    "extracted_info": None,
                    "answer": "",
                    "manager_alert": None
                }
                
                # Запускаем граф и обрабатываем поток событий
                # Используем ainvoke для получения финального состояния
                # (astream используется для потоковой обработки, но нам нужен финальный результат)
                final_state = await app.ainvoke(input_data, config)
                
                # Извлекаем ответ из финального состояния
                answer = final_state.get("answer", "")
                manager_alert = final_state.get("manager_alert")
                
                logger.info(f"Получен ответ от графа, длина: {len(answer)}")
                
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
                
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения через LangGraph: {e}", exc_info=True)
            return {
                "user_message": "Извините, произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте еще раз."
            }
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через LangGraph"""
        return await self.send_to_agent_langgraph(chat_id, user_text)
    
    async def reset_context(self, chat_id: str):
        """
        Полный сброс контекста для чата через физическое удаление чекпоинтов из БД.
        
        Удаляет все записи чекпоинтов для пользователя из PostgreSQL,
        что обеспечивает полную очистку памяти, как будто пользователь пишет впервые.
        """
        try:
            # Получаем telegram_user_id из chat_id
            try:
                telegram_user_id = int(chat_id)
            except ValueError:
                logger.error(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id")
                telegram_user_id = 0
            
            logger.info(f"Полный сброс контекста для chat_id={chat_id}, telegram_user_id={telegram_user_id}")
            
            # Физически удаляем все чекпоинты из БД для этого thread_id
            await clear_thread_memory(str(telegram_user_id))
            
            logger.info(f"Память полностью очищена для telegram_user_id={telegram_user_id}")
            
            # Очищаем историю результатов инструментов
            try:
                from .tool_history_service import get_tool_history_service
                tool_history_service = get_tool_history_service()
                tool_history_service.clear_history(chat_id)
                logger.debug(f"История результатов инструментов очищена для chat_id={chat_id}")
            except Exception as e:
                logger.debug(f"Ошибка при очистке истории результатов инструментов: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка при сбросе контекста: {e}", exc_info=True)
            raise
