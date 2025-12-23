"""
Основной граф состояний для обработки всех стадий диалога (Responses API)
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .conversation_state import ConversationState
from .utils import messages_to_history, filter_history_for_stage_detector
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.view_my_booking_agent import ViewMyBookingAgent

from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


def create_main_graph(langgraph_service: LangGraphService, checkpointer):
    """
    Создает и компилирует основной граф состояний
    
    Args:
        langgraph_service: Сервис LangGraph
        checkpointer: Обязательный checkpointer для сохранения состояния в PostgreSQL
        
    Returns:
        Скомпилированный граф
        
    Raises:
        ValueError: Если checkpointer не передан
    """
    if checkpointer is None:
        raise ValueError("checkpointer обязателен для работы с PostgreSQL. Граф должен компилироваться с checkpointer.")
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
    
    def __init__(self, langgraph_service: LangGraphService, checkpointer):
        """
        Инициализация графа с обязательным checkpointer
        
        Args:
            langgraph_service: Сервис LangGraph
            checkpointer: Обязательный checkpointer для сохранения состояния в PostgreSQL
            
        Raises:
            ValueError: Если checkpointer не передан
        """
        if checkpointer is None:
            raise ValueError("checkpointer обязателен для работы с PostgreSQL. Граф должен компилироваться с checkpointer.")
        
        self.langgraph_service = langgraph_service
        # КРИТИЧНО: сохраняем checkpointer для передачи в BookingAgent при каждом вызове
        # Это необходимо, так как checkpointer привязан к пулу соединений, который должен быть активен
        self.checkpointer = checkpointer
        
        # Используем кэш для агентов
        cache_key = id(langgraph_service)
        
        if cache_key not in MainGraph._agents_cache:
            # Создаём агентов только если их ещё нет в кэше
            # ВАЖНО: BookingAgent НЕ получает checkpointer при создании, он будет передаваться динамически
            MainGraph._agents_cache[cache_key] = {
                'stage_detector': StageDetectorAgent(langgraph_service),
                'booking': BookingAgent(langgraph_service),  # Без checkpointer при создании
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
        # КРИТИЧНО: компилируем граф С checkpointer для сохранения в PostgreSQL
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
        """Узел определения стадии (Silent Node - не добавляет messages в историю)"""
        logger.info("Определение стадии диалога")
        
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = messages_to_history(messages) if messages else None
        
        # Фильтруем историю для StageDetector: удаляем tool сообщения и ограничиваем до 10 последних
        if history:
            history = filter_history_for_stage_detector(history, max_messages=10)
        
        chat_id = state.get("chat_id")
        
        # Используем новый метод run() для получения всех сообщений
        result = self.stage_detector.run(message, history, chat_id=chat_id)
        
        # Получаем все новые сообщения из результата (но НЕ возвращаем их в messages)
        new_messages = result.get("messages", [])
        
        # Проверяем, был ли вызван CallManager
        if result.get("call_manager"):
            escalation_result = self.stage_detector._call_manager_result if hasattr(self.stage_detector, '_call_manager_result') and self.stage_detector._call_manager_result else {}
            logger.info(f"CallManager был вызван в StageDetectorAgent, chat_id: {chat_id}")
            
            # Получаем полную информацию о tool_calls (если есть)
            tool_results = result.get("tool_calls", [])
            
            # ВАЖНО: Если CallManager был вызван, это инструмент, поэтому возвращаем messages
            # (CallManager - это реальный вызов инструмента, который должен быть в истории)
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем messages только при вызове инструмента
                "answer": escalation_result.get("user_message", result.get("reply", "")),
                "manager_alert": escalation_result.get("manager_alert", result.get("manager_alert")),
                "agent_name": "StageDetectorAgent",
                "used_tools": ["CallManager"],
                "tool_results": tool_results,
            }
        
        # Определяем стадию через detect_stage (для обратной совместимости)
        stage_detection = self.stage_detector.detect_stage(message, history, chat_id=chat_id)
        
        # ВАЖНО: Роутер - это "тихий" узел, он НЕ должен добавлять промежуточные сообщения в историю
        # Возвращаем только stage для маршрутизации
        return {
            "stage": stage_detection.stage
            # НЕ возвращаем messages - это промежуточные "размышления" роутера, не нужные в истории
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
    
    def _process_agent_result(self, agent, message: str, history, chat_id: str, state: ConversationState, agent_name: str) -> ConversationState:
        """
        Обработка результата агента с проверкой на CallManager
        
        Args:
            agent: Экземпляр агента
            message: Сообщение пользователя
            history: История сообщений
            chat_id: ID чата
            state: Текущее состояние графа
            agent_name: Имя агента
            
        Returns:
            Обновленное состояние графа с messages из orchestrator
        """
        # Используем новый метод run() для получения всех сообщений
        result = agent.run(message, history, chat_id=chat_id)
        
        # Получаем все новые сообщения из результата
        new_messages = result.get("messages", [])
        
        # Получаем полную информацию о tool_calls
        tool_results = result.get("tool_calls", [])
        used_tools = [tool.get("name") for tool in tool_results] if tool_results else []
        
        # Проверяем, был ли вызван CallManager через инструмент
        if result.get("call_manager"):
            escalation_result = agent._call_manager_result if hasattr(agent, '_call_manager_result') and agent._call_manager_result else {}
            chat_id = state.get("chat_id", "unknown")
            
            logger.info(f"CallManager был вызван через инструмент в агенте {agent_name}, chat_id: {chat_id}")
            
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": escalation_result.get("user_message", result.get("reply", "")),
                "manager_alert": escalation_result.get("manager_alert", result.get("manager_alert")),
                "agent_name": agent_name,
                "used_tools": used_tools,
                "tool_results": tool_results,
            }
        
        # Обычный ответ агента
        answer = result.get("reply", "")
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
            "answer": answer,
            "agent_name": agent_name,
            "used_tools": used_tools,
            "tool_results": tool_results,
        }
    
    def _handle_booking(self, state: ConversationState) -> ConversationState:
        """Обработка бронирования через граф состояний"""
        logger.info("Обработка бронирования через граф")
        
        # КРИТИЧНО: передаем checkpointer в process_booking для создания графа с активным пулом
        # Это необходимо, так как checkpointer привязан к пулу соединений, который должен быть активен
        return self.booking_agent.process_booking(state, checkpointer=self.checkpointer)
    
    def _handle_cancellation_request(self, state: ConversationState) -> ConversationState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = messages_to_history(messages) if messages else None
        chat_id = state.get("chat_id")
        
        return self._process_agent_result(self.cancel_agent, message, history, chat_id, state, "CancelBookingAgent")
    
    def _handle_reschedule(self, state: ConversationState) -> ConversationState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = messages_to_history(messages) if messages else None
        chat_id = state.get("chat_id")
        
        return self._process_agent_result(self.reschedule_agent, message, history, chat_id, state, "RescheduleAgent")
    
    def _handle_view_my_booking(self, state: ConversationState) -> ConversationState:
        """Обработка просмотра записей"""
        logger.info("Обработка просмотра записей")
        message = state["message"]
        # Преобразуем messages в history для обратной совместимости с агентами
        messages = state.get("messages", [])
        history = messages_to_history(messages) if messages else None
        chat_id = state.get("chat_id")
        
        return self._process_agent_result(self.view_my_booking_agent, message, history, chat_id, state, "ViewMyBookingAgent")

