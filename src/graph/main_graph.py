"""
Основной граф состояний для обработки всех стадий диалога (Responses API)
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .conversation_state import ConversationState
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.view_my_booking_agent import ViewMyBookingAgent

from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


def create_main_graph(langgraph_service: LangGraphService, checkpointer=None):
    """
    Создает и компилирует основной граф состояний
    
    Args:
        langgraph_service: Сервис LangGraph
        checkpointer: Опциональный checkpointer для сохранения состояния
        
    Returns:
        Скомпилированный граф
    """
    main_graph = MainGraph(langgraph_service, checkpointer=checkpointer)
    return main_graph.compiled_graph


class MainGraph:
    """Основной граф состояний для обработки всех стадий диалога"""
    
    # Кэш для агентов (чтобы не создавать их заново при каждом создании графа)
    _agents_cache = {}
    
    @classmethod
    def clear_cache(cls):
        """Очистить кэш агентов"""
        cls._agents_cache.clear()
    
    def __init__(self, langgraph_service: LangGraphService, checkpointer=None):
        self.langgraph_service = langgraph_service
        
        # Используем кэш для агентов
        cache_key = id(langgraph_service)
        
        if cache_key not in MainGraph._agents_cache:
            # Создаём агентов только если их ещё нет в кэше
            MainGraph._agents_cache[cache_key] = {
                'stage_detector': StageDetectorAgent(langgraph_service),
                'booking': BookingAgent(langgraph_service),
                'cancellation_request': CancelBookingAgent(langgraph_service),
                'reschedule': RescheduleAgent(langgraph_service),
                'view_my_booking': ViewMyBookingAgent(langgraph_service),
            }
        
        # Используем агентов из кэша
        agents = MainGraph._agents_cache[cache_key]
        self.stage_detector = agents['stage_detector']
        self.booking_agent = agents['booking']
        self.cancel_agent = agents['cancellation_request']
        self.reschedule_agent = agents['reschedule']
        self.view_my_booking_agent = agents['view_my_booking']
        
        # Создаём граф
        self.graph = self._create_graph()
        self.compiled_graph = self.graph.compile(checkpointer=checkpointer)
    
    def _create_graph(self) -> StateGraph:
        """Создание графа состояний"""
        graph = StateGraph(ConversationState)
        
        # Добавляем узлы
        graph.add_node("detect_stage", self._detect_stage)
        graph.add_node("handle_booking", self._handle_booking)
        graph.add_node("handle_cancellation_request", self._handle_cancellation_request)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        graph.add_node("handle_view_my_booking", self._handle_view_my_booking)
        
        # Добавляем рёбра
        graph.add_edge(START, "detect_stage")
        graph.add_conditional_edges(
            "detect_stage",
            self._route_after_detect,
            {
                "booking": "handle_booking",
                "cancellation_request": "handle_cancellation_request",
                "reschedule": "handle_reschedule",
                "view_my_booking": "handle_view_my_booking",
                "end": END
            }
        )
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_cancellation_request", END)
        graph.add_edge("handle_reschedule", END)
        graph.add_edge("handle_view_my_booking", END)
        return graph
    
    def _detect_stage(self, state: ConversationState) -> ConversationState:
        """Узел определения стадии"""
        logger.info("Определение стадии диалога")
        
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = []
        if messages:
            for msg in messages:
                # Если это словарь (старый формат)
                if isinstance(msg, dict):
                    history.append({
                        "role": msg.get("role", "user"), 
                        "content": msg.get("content", "")
                    })
                # Если это объект LangChain (новый формат)
                else:
                    # Маппинг типов LangChain в наши роли
                    role = "user"
                    if hasattr(msg, "type"):
                        if msg.type == "ai": role = "assistant"
                        elif msg.type == "system": role = "system"
                        elif msg.type == "tool": role = "tool"
                        elif msg.type == "human": role = "user"
                    
                    history.append({
                        "role": role, 
                        "content": getattr(msg, "content", "")
                    })
        chat_id = state.get("chat_id")
        
        # Определяем стадию
        stage_detection = self.stage_detector.detect_stage(message, history, chat_id=chat_id)
        
        # Проверяем, был ли вызван CallManager в StageDetectorAgent
        if hasattr(self.stage_detector, '_call_manager_result') and self.stage_detector._call_manager_result:
            escalation_result = self.stage_detector._call_manager_result
            logger.info(f"CallManager был вызван в StageDetectorAgent, chat_id: {chat_id}")
            
            # Получаем полную информацию о tool_calls (если есть)
            tool_results = self.stage_detector._last_tool_calls if hasattr(self.stage_detector, '_last_tool_calls') and self.stage_detector._last_tool_calls else []
            
            return {
                "answer": escalation_result.get("user_message"),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": "StageDetectorAgent",
                "used_tools": ["CallManager"],
                "tool_results": tool_results,
            }
        
        return {
            "stage": stage_detection.stage
        }
    
    def _route_after_detect(self, state: ConversationState) -> Literal[
        "booking",
        "cancellation_request", "reschedule", "view_my_booking", "end"
    ]:
        """Маршрутизация после определения стадии"""
        # Если CallManager был вызван, завершаем граф
        if state.get("answer") and state.get("manager_alert"):
            logger.info("CallManager был вызван в StageDetectorAgent, завершаем граф")
            return "end"
        
        # Иначе маршрутизируем по стадии
        stage = state.get("stage", "booking")
        logger.info(f"Маршрутизация на стадию: {stage}")
        
        # Валидация стадии
        valid_stages = [
            "booking",
            "cancellation_request", "reschedule", "view_my_booking"
        ]
        
        if stage not in valid_stages:
            logger.warning(f"⚠️ Неизвестная стадия: {stage}, устанавливаю booking")
            return "booking"
        
        return stage
    
    def _process_agent_result(self, agent, answer: str, state: ConversationState, agent_name: str) -> ConversationState:
        """
        Обработка результата агента с проверкой на CallManager
        
        Args:
            agent: Экземпляр агента
            answer: Ответ агента
            state: Текущее состояние графа
            agent_name: Имя агента
            
        Returns:
            Обновленное состояние графа
        """
        # Получаем полную информацию о tool_calls (не только имена)
        tool_results = agent._last_tool_calls if hasattr(agent, '_last_tool_calls') and agent._last_tool_calls else []
        used_tools = [tool["name"] for tool in tool_results] if tool_results else []
        
        # Агент теперь возвращает просто строку (ответ)
        answer_text = answer
        
        # Проверяем, был ли вызван CallManager через инструмент
        if answer_text == "[CALL_MANAGER_RESULT]" and hasattr(agent, '_call_manager_result') and agent._call_manager_result:
            escalation_result = agent._call_manager_result
            chat_id = state.get("chat_id", "unknown")
            
            logger.info(f"CallManager был вызван через инструмент в агенте {agent_name}, chat_id: {chat_id}")
            
            return {
                "answer": escalation_result.get("user_message"),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": agent_name,
                "used_tools": used_tools,
                "tool_results": tool_results,
            }
        
        # Обычный ответ агента
        answer = answer_text
        
        return {
            "answer": answer,
            "agent_name": agent_name,
            "used_tools": used_tools,
            "tool_results": tool_results,
        }
    
    def _handle_booking(self, state: ConversationState) -> ConversationState:
        """Обработка бронирования через граф состояний"""
        logger.info("Обработка бронирования через граф")
        
        # Используем новый метод process_booking, который работает с графом
        return self.booking_agent.process_booking(state)
    
    def _handle_cancellation_request(self, state: ConversationState) -> ConversationState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = []
        if messages:
            for msg in messages:
                # Если это словарь (старый формат)
                if isinstance(msg, dict):
                    history.append({
                        "role": msg.get("role", "user"), 
                        "content": msg.get("content", "")
                    })
                # Если это объект LangChain (новый формат)
                else:
                    # Маппинг типов LangChain в наши роли
                    role = "user"
                    if hasattr(msg, "type"):
                        if msg.type == "ai": role = "assistant"
                        elif msg.type == "system": role = "system"
                        elif msg.type == "tool": role = "tool"
                        elif msg.type == "human": role = "user"
                    
                    history.append({
                        "role": role, 
                        "content": getattr(msg, "content", "")
                    })
        chat_id = state.get("chat_id")
        
        agent_result = self.cancel_agent(message, history, chat_id=chat_id)
        return self._process_agent_result(self.cancel_agent, agent_result, state, "CancelBookingAgent")
    
    def _handle_reschedule(self, state: ConversationState) -> ConversationState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = []
        if messages:
            for msg in messages:
                # Если это словарь (старый формат)
                if isinstance(msg, dict):
                    history.append({
                        "role": msg.get("role", "user"), 
                        "content": msg.get("content", "")
                    })
                # Если это объект LangChain (новый формат)
                else:
                    # Маппинг типов LangChain в наши роли
                    role = "user"
                    if hasattr(msg, "type"):
                        if msg.type == "ai": role = "assistant"
                        elif msg.type == "system": role = "system"
                        elif msg.type == "tool": role = "tool"
                        elif msg.type == "human": role = "user"
                    
                    history.append({
                        "role": role, 
                        "content": getattr(msg, "content", "")
                    })
        chat_id = state.get("chat_id")
        
        agent_result = self.reschedule_agent(message, history, chat_id=chat_id)
        return self._process_agent_result(self.reschedule_agent, agent_result, state, "RescheduleAgent")
    
    def _handle_view_my_booking(self, state: ConversationState) -> ConversationState:
        """Обработка просмотра записей"""
        logger.info("Обработка просмотра записей")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = []
        if messages:
            for msg in messages:
                # Если это словарь (старый формат)
                if isinstance(msg, dict):
                    history.append({
                        "role": msg.get("role", "user"), 
                        "content": msg.get("content", "")
                    })
                # Если это объект LangChain (новый формат)
                else:
                    # Маппинг типов LangChain в наши роли
                    role = "user"
                    if hasattr(msg, "type"):
                        if msg.type == "ai": role = "assistant"
                        elif msg.type == "system": role = "system"
                        elif msg.type == "tool": role = "tool"
                        elif msg.type == "human": role = "user"
                    
                    history.append({
                        "role": role, 
                        "content": getattr(msg, "content", "")
                    })
        chat_id = state.get("chat_id")
        
        agent_result = self.view_my_booking_agent(message, history, chat_id=chat_id)
        return self._process_agent_result(self.view_my_booking_agent, agent_result, state, "ViewMyBookingAgent")

