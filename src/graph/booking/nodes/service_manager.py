"""
Узел менеджера услуг для выбора услуги в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ..state import BookingSubState, DialogStep
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструменты
from ....agents.tools.get_categories.tool import GetCategories
from ....agents.tools.get_services.tool import GetServices
from ....agents.tools.find_service.tool import FindService
from ....agents.tools.find_master_by_service.tool import FindMasterByService


SYSTEM_PROMPT = """Ты — AI-администратор салона красоты LookTown. Сейчас этап выбора услуги.
Твой стиль общения — дружелюбный, профессиональный, краткий. Общайся на "вы", от женского лица.

ТВОЯ ЗАДАЧА: Помочь клиенту выбрать услугу, чтобы мы получили её ID.

ИНСТРУКЦИЯ (Выполняй строго по пунктам):
1.1 Если клиент сказал на какую категорию хочет записаться (например, "хочу на маникюр"), покажи полный список услуг этой категории, используя инструмент `GetServices`.
1.2 Если клиент просто выразил желание записаться или узнать услуги салона, покажи полный список категорий, используя инструмент `GetCategories`.
1.3 Если Клиент хочет записаться к конкретному мастеру (называет имя и услугу) — используй `FindMasterByService`. Если только имя — сначала уточни услугу.
1.4 Если ты не нашёл нужную услугу в GetServices или запрос специфичный — используй `FindService`.

ВАЖНО:
- Не придумывай услуги и цены. Бери только из инструментов.
- Твоя цель — вывести список, чтобы клиент мог написать "Хочу вот эту" (и тогда Анализатор на следующем шаге поймает ID)."""


def service_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера услуг для выбора услуги в процессе бронирования
    
    Этот узел запускается, если service_id в состоянии бронирования все еще None.
    Использует инструменты GetCategories, GetServices, FindService, FindMasterByService
    для помощи клиенту в выборе услуги.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer
    """
    logger.info("Запуск узла service_manager")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Проверяем, есть ли уже service_id
    service_id = booking_state.get("service_id")
    if service_id is not None:
        logger.info(f"Услуга уже выбрана (service_id={service_id}), пропускаем service_manager")
        return {}
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    history = state.get("history") or []
    chat_id = state.get("chat_id")
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем необходимые инструменты
        tools_registry.register_tool(GetCategories)
        tools_registry.register_tool(GetServices)
        tools_registry.register_tool(FindService)
        tools_registry.register_tool(FindMasterByService)
        
        # Создаем orchestrator
        config = ResponsesAPIConfig()
        orchestrator = ResponsesOrchestrator(
            instructions=SYSTEM_PROMPT,
            tools_registry=tools_registry,
            config=config
        )
        
        # Запускаем один ход диалога
        result = orchestrator.run_turn(
            user_message=user_message,
            history=history,
            chat_id=chat_id
        )
        
        # Получаем ответ
        reply = result.get("reply", "")
        tool_calls = result.get("tool_calls", [])
        
        # Проверяем, был ли вызван CallManager
        if result.get("call_manager"):
            logger.info("CallManager был вызван в service_manager_node")
            return {
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else []
            }
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Service manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        
        return {
            "answer": reply,
            "used_tools": used_tools
        }
        
    except Exception as e:
        logger.error(f"Ошибка в service_manager_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при выборе услуги. Попробуйте еще раз."
        }
