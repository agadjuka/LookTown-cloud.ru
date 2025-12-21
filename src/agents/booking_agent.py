"""
Агент для обработки бронирований
"""
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService
from ..graph.conversation_state import ConversationState
from ..graph.booking.state import BookingSubState
from ..graph.booking.graph import create_booking_graph
from ..services.logger_service import logger


class BookingAgent(BaseAgent):
    """Агент для работы с бронированиями"""
    
    def __init__(self, langgraph_service: LangGraphService):
        """
        Инициализация агента бронирования
        
        Args:
            langgraph_service: Сервис LangGraph
        """
        # Сохраняем langgraph_service для создания графа
        self.langgraph_service = langgraph_service
        
        # Инициализируем BaseAgent с пустыми инструментами (они теперь в узлах графа)
        super().__init__(
            langgraph_service=langgraph_service,
            instruction="",  # Не используется, так как логика в графе
            tools=[],
            agent_name="Агент бронирования"
        )
    
    def process_booking(self, state: ConversationState, checkpointer) -> ConversationState:
        """
        Обработка бронирования через граф состояний
        
        Args:
            state: Текущее состояние диалога
            checkpointer: Checkpointer для сохранения состояния в PostgreSQL
                         Должен быть передан из MainGraph, так как привязан к активному пулу соединений
            
        Returns:
            Обновленное состояние диалога с ответом и обновленными данными бронирования
        """
        if checkpointer is None:
            raise ValueError("checkpointer обязателен для работы с PostgreSQL. Должен быть передан из MainGraph.")
        
        logger.info("Запуск обработки бронирования через граф")
        
        try:
            # КРИТИЧНО: создаем граф динамически с checkpointer, который привязан к активному пулу
            # Не кэшируем граф, так как checkpointer привязан к пулу, который может быть закрыт
            booking_graph = create_booking_graph(checkpointer=checkpointer)
            # Извлекаем текущее состояние бронирования из extracted_info
            extracted_info = state.get("extracted_info") or {}
            booking_data = extracted_info.get("booking", {})
            
            logger.debug(f"Текущее booking_data из extracted_info: {booking_data}")
            
            # Создаем начальное BookingSubState
            booking_state: BookingSubState = {
                "service_id": booking_data.get("service_id"),
                "service_name": booking_data.get("service_name"),
                "master_id": booking_data.get("master_id"),
                "master_name": booking_data.get("master_name"),
                "slot_time": booking_data.get("slot_time"),
                "client_name": booking_data.get("client_name"),
                "client_phone": booking_data.get("client_phone"),
                "is_finalized": booking_data.get("is_finalized", False)
            }
            
            logger.debug(f"Начальное booking_state для графа: {booking_state}")
            
            # КРИТИЧНО: Проверяем, что messages передаются в booking граф
            messages = state.get("messages", [])
            
            # Создаем состояние для графа (с booking и conversation)
            graph_state = {
                "booking": booking_state,
                "conversation": state  # Включает messages с ToolMessage
            }
            
            # КРИТИЧНО: извлекаем chat_id из состояния и создаем config с thread_id
            # Это необходимо для работы checkpointer с PostgreSQL
            chat_id = state.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id обязателен для работы с checkpointer")
            
            # Преобразуем chat_id в telegram_user_id (они равны для личных чатов)
            try:
                telegram_user_id = int(chat_id)
            except (ValueError, TypeError):
                logger.warning(f"Не удалось преобразовать chat_id={chat_id} в telegram_user_id, используем как есть")
                telegram_user_id = chat_id
            
            # Создаем config с thread_id для checkpointer
            # КРИТИЧНО: thread_id обязателен для работы checkpointer с PostgreSQL
            config = {"configurable": {"thread_id": str(telegram_user_id)}}
            
            # Запускаем граф с config для сохранения состояния в PostgreSQL
            # LangGraph автоматически обработает синхронный вызов с асинхронным checkpointer
            result_state = booking_graph.invoke(graph_state, config=config)
            
            # Извлекаем обновленное состояние бронирования
            updated_booking_state = result_state.get("booking", booking_state)
            
            logger.debug(f"Обновленное booking_state из графа: {updated_booking_state}")
            
            # Извлекаем обновленное состояние диалога (с answer и другими полями)
            updated_conversation_state = result_state.get("conversation", state)
            
            # Обновляем extracted_info с новыми данными бронирования
            # Используем extracted_info из обновленного conversation_state, если он есть
            updated_extracted_info = updated_conversation_state.get("extracted_info")
            if updated_extracted_info is None:
                # Если нет, создаем копию исходного
                updated_extracted_info = extracted_info.copy()
            
            # Всегда обновляем booking данными из графа (они самые актуальные)
            updated_extracted_info = updated_extracted_info.copy()
            updated_extracted_info["booking"] = dict(updated_booking_state)
            
            logger.debug(f"Финальное extracted_info.booking: {updated_extracted_info.get('booking')}")
            
            # Извлекаем answer и другие поля из обновленного conversation_state
            answer = updated_conversation_state.get("answer", "")
            manager_alert = updated_conversation_state.get("manager_alert")
            used_tools = updated_conversation_state.get("used_tools")
            tool_results = updated_conversation_state.get("tool_results")
            
            # КРИТИЧНО: Извлекаем messages из updated_conversation_state (включая ToolMessage из узлов)
            updated_messages = updated_conversation_state.get("messages", state.get("messages", []))
            
            # Создаем обновленное ConversationState
            updated_state: ConversationState = {
                **state,
                "messages": updated_messages,  # КРИТИЧНО: Используем messages из booking графа (с ToolMessage)
                "extracted_info": updated_extracted_info,
                "answer": answer,
                "manager_alert": manager_alert,
                "used_tools": used_tools,
                "tool_results": tool_results,
                "agent_name": "BookingAgent"
            }
            
            logger.info("Обработка бронирования завершена")
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Ошибка в process_booking: {e}", exc_info=True)
            return {
                **state,
                "answer": "Извините, произошла ошибка при обработке бронирования. Попробуйте еще раз.",
                "agent_name": "BookingAgent"
            }
    
    def __call__(self, message: str, history: Optional[List[Dict[str, Any]]] = None, chat_id: Optional[str] = None) -> str:
        """
        Выполнение запроса к агенту (совместимость со старым API)
        
        Этот метод создает ConversationState и вызывает process_booking,
        затем возвращает только answer для совместимости со старым кодом.
        
        Args:
            message: Сообщение пользователя
            history: История сообщений (преобразованная из LangGraph messages)
            chat_id: ID чата
            
        Returns:
            Ответ агента (строка)
        """
        # Преобразуем history в messages для новой структуры
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        messages = []
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    ai_msg = AIMessage(content=content)
                    if msg.get("tool_calls"):
                        ai_msg.tool_calls = msg.get("tool_calls")
                    messages.append(ai_msg)
                elif role == "tool":
                    tool_msg = ToolMessage(
                        content=content,
                        tool_call_id=msg.get("tool_call_id", "")
                    )
                    messages.append(tool_msg)
        
        # Добавляем текущее сообщение
        messages.append(HumanMessage(content=message))
        
        # Создаем ConversationState из параметров
        state: ConversationState = {
            "messages": messages,
            "message": message,
            "chat_id": chat_id,
            "stage": None,
            "extracted_info": None,
            "answer": "",
            "manager_alert": None,
            "agent_name": None,
            "used_tools": None
        }
        
        # Обрабатываем через граф
        result_state = self.process_booking(state)
        
        # Возвращаем только answer для совместимости
        return result_state.get("answer", "")
