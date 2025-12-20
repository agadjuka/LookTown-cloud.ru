"""
Агент для обработки бронирований
"""
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService
from ..graph.conversation_state import ConversationState
from ..graph.booking.state import BookingSubState, DialogStep
from ..graph.booking.graph import create_booking_graph
from ..services.logger_service import logger


class BookingAgent(BaseAgent):
    """Агент для работы с бронированиями"""
    
    def __init__(self, langgraph_service: LangGraphService):
        # Сохраняем langgraph_service для создания графа
        self.langgraph_service = langgraph_service
        
        # Создаем граф бронирования (ленивая инициализация)
        self._booking_graph = None
        
        # Инициализируем BaseAgent с пустыми инструментами (они теперь в узлах графа)
        super().__init__(
            langgraph_service=langgraph_service,
            instruction="",  # Не используется, так как логика в графе
            tools=[],
            agent_name="Агент бронирования"
        )
    
    @property
    def booking_graph(self):
        """Ленивая инициализация графа бронирования"""
        if self._booking_graph is None:
            self._booking_graph = create_booking_graph()
        return self._booking_graph
    
    def process_booking(self, state: ConversationState) -> ConversationState:
        """
        Обработка бронирования через граф состояний
        
        Args:
            state: Текущее состояние диалога
            
        Returns:
            Обновленное состояние диалога с ответом и обновленными данными бронирования
        """
        logger.info("Запуск обработки бронирования через граф")
        
        try:
            # Извлекаем текущее состояние бронирования из extracted_info
            extracted_info = state.get("extracted_info") or {}
            booking_data = extracted_info.get("booking", {})
            
            # Создаем начальное BookingSubState
            booking_state: BookingSubState = {
                "service_id": booking_data.get("service_id"),
                "service_name": booking_data.get("service_name"),
                "master_id": booking_data.get("master_id"),
                "master_name": booking_data.get("master_name"),
                "slot_time": booking_data.get("slot_time"),
                "client_name": booking_data.get("client_name"),
                "client_phone": booking_data.get("client_phone"),
                "dialog_step": booking_data.get("dialog_step", DialogStep.SERVICE.value),
                "is_finalized": booking_data.get("is_finalized", False)
            }
            
            # Создаем состояние для графа (с booking и conversation)
            graph_state = {
                "booking": booking_state,
                "conversation": state
            }
            
            # Запускаем граф
            result_state = self.booking_graph.invoke(graph_state)
            
            # Извлекаем обновленное состояние бронирования
            updated_booking_state = result_state.get("booking", booking_state)
            
            # Извлекаем обновленное состояние диалога (с answer и другими полями)
            updated_conversation_state = result_state.get("conversation", state)
            
            # Обновляем extracted_info с новыми данными бронирования
            updated_extracted_info = updated_conversation_state.get("extracted_info") or extracted_info.copy()
            if "booking" not in updated_extracted_info:
                updated_extracted_info["booking"] = dict(updated_booking_state)
            
            # Извлекаем answer и другие поля из обновленного conversation_state
            answer = updated_conversation_state.get("answer", "")
            manager_alert = updated_conversation_state.get("manager_alert")
            used_tools = updated_conversation_state.get("used_tools")
            
            # Создаем обновленное ConversationState
            updated_state: ConversationState = {
                **state,
                "extracted_info": updated_extracted_info,
                "answer": answer,
                "manager_alert": manager_alert,
                "used_tools": used_tools,
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
            history: История сообщений
            chat_id: ID чата
            
        Returns:
            Ответ агента (строка)
        """
        # Создаем ConversationState из параметров
        state: ConversationState = {
            "message": message,
            "chat_id": chat_id,
            "conversation_id": None,
            "history": history,
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
