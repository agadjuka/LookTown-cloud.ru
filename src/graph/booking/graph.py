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
    
    Критические поля (service_id, slot_time, master_id) обновляются даже если значение None
    (для поддержки явного сброса при смене темы).
    Остальные поля обновляются только если значение не None.
    
    Args:
        conversation_state: Состояние после выполнения узла
        current_booking_state: Текущее состояние бронирования (базовые значения)
        
    Returns:
        Обновленное BookingSubState
    """
    # Извлекаем booking данные из extracted_info
    extracted_info = conversation_state.get("extracted_info") or {}
    booking_data = extracted_info.get("booking", {})
    
    # Объединяем с текущим состоянием
    updated_state = dict(current_booking_state)
    
    # Критические поля, которые могут быть явно сброшены в None
    critical_fields = {"service_id", "slot_time", "master_id", "master_name", "slot_time_verified"}
    
    for key, value in booking_data.items():
        # Для критических полей обновляем даже если значение None (явный сброс)
        if key in critical_fields:
            updated_state[key] = value
        # Для остальных полей обновляем только если значение не None и не пустое
        elif value is not None and value != "":
            updated_state[key] = value
        # Если значение None в booking_data для некритических полей, оставляем текущее значение
    
    logger.debug(f"_conversation_state_to_booking_substate: current={current_booking_state}, booking_data={booking_data}, result={updated_state}")
    
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


def route_after_slot_manager(state: Dict[str, Any]) -> Literal["contact_collector", "finalizer", END]:
    """
    Функция роутинга после slot_manager
    
    Логика:
    - Если slot_time_verified = True → роутим дальше (contact_collector или finalizer)
    - Иначе → END (либо предложили слоты, либо время недоступно - уже написали сообщение)
    
    Args:
        state: Состояние графа (словарь с ключом 'booking')
        
    Returns:
        "contact_collector", "finalizer" или END
    """
    booking_state = state.get("booking", {})
    slot_time_verified = booking_state.get("slot_time_verified", False)
    
    if slot_time_verified:
        # Время проверено и доступно - роутим дальше по состоянию
        logger.info("slot_time_verified=True, роутим дальше по состоянию")
        
        # Проверяем контакты
        if not booking_state.get("client_name") or not booking_state.get("client_phone"):
            logger.info("Контактные данные неполные, маршрутизируем в contact_collector")
            return "contact_collector"
        else:
            logger.info("Все данные собраны, маршрутизируем в finalizer")
            return "finalizer"
    else:
        logger.info("slot_manager завершил работу (предложил слоты или время недоступно), завершаем граф")
        return END


def route_booking(state: Dict[str, Any]) -> Literal["service_manager", "slot_manager", "contact_collector", "finalizer", END]:
    """
    Функция роутинга для выбора следующего узла в графе бронирования
    
    Data-Driven Routing: роутинг основан только на наличии данных в состоянии.
    Если Analyzer сбросит service_id в None (при смене темы), роутер автоматически
    вернет "service_manager", игнорируя предыдущий этап.
    
    Логика (строгий порядок проверок):
    1. Если is_finalized -> END (процесс завершен)
    2. Если service_id is None -> service_manager (даже если есть service_name, ID важнее)
    3. Если slot_time is None -> slot_manager (поиск слотов)
    4. Если slot_time есть, но slot_time_verified is False/None -> slot_manager (проверка доступности)
    5. Если нет контактов (client_name или client_phone) -> contact_collector
    6. Иначе (все данные есть) -> finalizer
    
    Args:
        state: Состояние графа (словарь с ключом 'booking')
        
    Returns:
        Имя следующего узла или END
    """
    booking_state = state.get("booking", {})
    
    # Логируем текущее состояние для отладки
    service_id = booking_state.get("service_id")
    logger.debug(f"route_booking: service_id={service_id} (type={type(service_id)}, is None={service_id is None})")
    
    # 1. Если финализировано — выход
    if booking_state.get("is_finalized"):
        logger.info("Бронирование финализировано, завершаем граф")
        return END
    
    # 2. Если нет ID услуги — идем выбирать услугу (даже если есть название, ID важнее)
    # Используем явную проверку на None
    if service_id is None:
        logger.info(f"service_id отсутствует (значение: {service_id}), маршрутизируем в service_manager")
        return "service_manager"
    
    # 3. Проверка времени слота
    slot_time = booking_state.get("slot_time")
    slot_time_verified = booking_state.get("slot_time_verified", False)
    
    if slot_time is None:
        # Времени нет — идем искать слоты
        logger.info("slot_time отсутствует, маршрутизируем в slot_manager")
        return "slot_manager"
    elif not slot_time_verified:
        # Время указано, но не проверено — проверяем доступность
        logger.info(f"slot_time={slot_time} указан, но не проверен, маршрутизируем в slot_manager для проверки")
        return "slot_manager"
    
    # 4. Если нет контактов — собираем контакты
    if not booking_state.get("client_name") or not booking_state.get("client_phone"):
        logger.info("Контактные данные неполные, маршрутизируем в contact_collector")
        return "contact_collector"
    
    # 5. Иначе — финализируем (slot_time проверен и доступен)
    logger.info("Все данные собраны, маршрутизируем в finalizer")
    return "finalizer"


# Определяем тип состояния для графа
BookingGraphState = Dict[str, Any]


def create_booking_graph(checkpointer=None):
    """
    Создает и компилирует граф состояний для бронирования
    
    Args:
        checkpointer: Опциональный checkpointer для сохранения состояния
        
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
    workflow.add_edge("service_manager", END)  # После service_manager ждем ответа клиента
    workflow.add_conditional_edges("slot_manager", route_after_slot_manager)  # Условный роутинг после slot_manager
    workflow.add_edge("contact_collector", END)  # После contact_collector ждем ответа клиента
    workflow.add_edge("finalizer", END)  # Только finalizer завершает граф
    
    # Компилируем граф с checkpointer
    compiled_graph = workflow.compile(checkpointer=checkpointer)
    
    logger.info("Граф бронирования создан и скомпилирован")
    
    return compiled_graph

