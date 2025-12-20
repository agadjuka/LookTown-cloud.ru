"""
Граф состояний для подграфа бронирования (Booking Subgraph)
"""
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END
from ..conversation_state import ConversationState
from .state import BookingSubState
from .analyzer import booking_analyzer_node
from .nodes.service_manager import service_manager_node
from .nodes.slot_manager import slot_manager_node
from .nodes.contact_collector import contact_collector_node
from .nodes.finalizer import finalizer_node
from ...services.logger_service import logger


def _booking_substate_to_conversation_state(
    booking_state: BookingSubState,
    conversation_state: ConversationState
) -> ConversationState:
    """
    Преобразует BookingSubState в ConversationState для передачи в узлы
    
    Args:
        booking_state: Состояние подграфа бронирования
        conversation_state: Базовое состояние диалога (для message, history, chat_id и т.д.)
        
    Returns:
        ConversationState с booking данными в extracted_info
    """
    # Создаем extracted_info с booking данными
    extracted_info = conversation_state.get("extracted_info") or {}
    extracted_info = extracted_info.copy()
    extracted_info["booking"] = dict(booking_state)
    
    # Создаем полное ConversationState
    return {
        **conversation_state,
        "extracted_info": extracted_info
    }


def _conversation_state_to_booking_substate(
    conversation_state: ConversationState,
    current_booking_state: BookingSubState
) -> BookingSubState:
    """
    Извлекает BookingSubState из ConversationState после выполнения узла
    
    Args:
        conversation_state: Состояние после выполнения узла
        current_booking_state: Текущее состояние бронирования (базовые значения)
        
    Returns:
        Обновленное BookingSubState
    """
    # Извлекаем booking данные из extracted_info
    extracted_info = conversation_state.get("extracted_info") or {}
    booking_data = extracted_info.get("booking", {})
    
    # Объединяем с текущим состоянием (чтобы не потерять данные)
    updated_state = dict(current_booking_state)
    updated_state.update(booking_data)
    
    return updated_state


def _create_booking_state_adapter(original_node):
    """
    Создает адаптер для узла, который работает с ConversationState,
    чтобы он мог работать с BookingSubState в графе
    
    Args:
        original_node: Оригинальная функция узла (принимает ConversationState)
        
    Returns:
        Функция-адаптер (принимает BookingSubState и ConversationState, возвращает обновленное состояние)
    """
    def adapter(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Адаптер для узла
        
        Args:
            state: Словарь с ключами 'booking' (BookingSubState) и 'conversation' (ConversationState)
            
        Returns:
            Обновленное состояние с ключами 'booking' и 'conversation' (с answer и другими полями)
        """
        booking_state = state.get("booking", {})
        conversation_state = state.get("conversation", {})
        
        # Преобразуем BookingSubState в ConversationState
        full_conversation_state = _booking_substate_to_conversation_state(
            booking_state,
            conversation_state
        )
        
        # Вызываем оригинальный узел
        result = original_node(full_conversation_state)
        
        # Обновляем conversation_state с результатами узла
        updated_conversation_state = {**full_conversation_state, **result}
        
        # Извлекаем обновленное BookingSubState
        updated_booking_state = _conversation_state_to_booking_substate(
            updated_conversation_state,
            booking_state
        )
        
        # Возвращаем обновленное состояние с booking и conversation (включая answer, manager_alert и т.д.)
        return {
            "booking": updated_booking_state,
            "conversation": updated_conversation_state
        }
    
    return adapter


# Создаем адаптеры для всех узлов
analyzer_adapter = _create_booking_state_adapter(booking_analyzer_node)
service_manager_adapter = _create_booking_state_adapter(service_manager_node)
slot_manager_adapter = _create_booking_state_adapter(slot_manager_node)
contact_collector_adapter = _create_booking_state_adapter(contact_collector_node)
finalizer_adapter = _create_booking_state_adapter(finalizer_node)


def route_booking(state: Dict[str, Any]) -> Literal["service_manager", "slot_manager", "contact_collector", "finalizer", END]:
    """
    Функция роутинга для выбора следующего узла в графе бронирования
    
    Логика (строгий порядок проверок):
    1. Если is_finalized is True -> Возвращаем END (процесс завершен)
    2. Если service_id is None -> Возвращаем "service_manager"
    3. Если slot_time is None -> Возвращаем "slot_manager"
    4. Если client_name is None OR client_phone is None -> Возвращаем "contact_collector"
    5. Иначе (все данные есть) -> Возвращаем "finalizer"
    
    Args:
        state: Состояние графа (словарь с ключом 'booking')
        
    Returns:
        Имя следующего узла или END
    """
    booking_state = state.get("booking", {})
    
    # Проверка 1: Если is_finalized is True -> END
    if booking_state.get("is_finalized"):
        logger.info("Бронирование финализировано, завершаем граф")
        return END
    
    # Проверка 2: Если service_id is None -> service_manager
    if booking_state.get("service_id") is None:
        logger.info("service_id отсутствует, маршрутизируем в service_manager")
        return "service_manager"
    
    # Проверка 3: Если slot_time is None -> slot_manager
    if booking_state.get("slot_time") is None:
        logger.info("slot_time отсутствует, маршрутизируем в slot_manager")
        return "slot_manager"
    
    # Проверка 4: Если client_name is None OR client_phone is None -> contact_collector
    client_name = booking_state.get("client_name")
    client_phone = booking_state.get("client_phone")
    if client_name is None or client_phone is None:
        logger.info("Контактные данные неполные, маршрутизируем в contact_collector")
        return "contact_collector"
    
    # Проверка 5: Все данные есть -> finalizer
    logger.info("Все данные собраны, маршрутизируем в finalizer")
    return "finalizer"


# Определяем тип состояния для графа
BookingGraphState = Dict[str, Any]


def create_booking_graph() -> StateGraph:
    """
    Создает и компилирует граф состояний для бронирования
    
    Returns:
        Скомпилированный граф
    """
    logger.info("Создание графа бронирования")
    
    # Создаем граф
    workflow = StateGraph(BookingGraphState)
    
    # Добавляем узлы
    workflow.add_node("analyzer", analyzer_adapter)
    workflow.add_node("service_manager", service_manager_adapter)
    workflow.add_node("slot_manager", slot_manager_adapter)
    workflow.add_node("contact_collector", contact_collector_adapter)
    workflow.add_node("finalizer", finalizer_adapter)
    
    # Добавляем ребра
    workflow.add_edge(START, "analyzer")
    workflow.add_conditional_edges("analyzer", route_booking)
    workflow.add_edge("service_manager", END)
    workflow.add_edge("slot_manager", END)
    workflow.add_edge("contact_collector", END)
    workflow.add_edge("finalizer", END)
    
    # Компилируем граф
    compiled_graph = workflow.compile()
    
    logger.info("Граф бронирования создан и скомпилирован")
    
    return compiled_graph

