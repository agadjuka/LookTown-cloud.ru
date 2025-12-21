"""
Узел менеджера услуг для выбора услуги в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструменты
from ....agents.tools.get_categories.tool import GetCategories
from ....agents.tools.find_service.tool import FindService


def _build_system_prompt(
    service_id: Optional[int],
    service_name: Optional[str],
    master_id: Optional[int],
    master_name: Optional[str]
) -> str:
    """
    Формирует системный промпт для узла service_manager с контекстом
    
    Args:
        service_id: ID услуги (если есть)
        service_name: Название услуги (если есть)
        master_id: ID мастера (если есть)
        master_name: Имя мастера (если есть)
        
    Returns:
        Системный промпт для LLM
    """
    # Формируем секцию КОНТЕКСТ с заполненными полями
    context_parts = []
    
    if service_id is not None:
        context_parts.append(f"- Выбранная услуга ID: {service_id}")
    
    if service_name:
        context_parts.append(f"- Выбранная услуга: {service_name}")
    
    if master_id is not None:
        master_info = f"{master_id}"
        if master_name:
            master_info += f" ({master_name})"
        context_parts.append(f"- Выбранный мастер: {master_info}")
    elif master_name:
        context_parts.append(f"- Выбранный мастер: {master_name}")
    
    # Формируем контекстную секцию
    context_section = ""
    if context_parts:
        context_section = "\nКОНТЕКСТ:\n" + "\n".join(context_parts) + "\n"
    
    prompt = f"""Ты — AI-администратор салона красоты LookTown. Сейчас этап выбора услуги.
Твой стиль общения — дружелюбный, профессиональный, краткий. Общайся на "вы", от женского лица, здоровайся с клиентом, но только один раз.

ТВОЯ ЕДИНСТВЕННАЯ ЗАДАЧА: Помочь клиенту выбрать услугу, чтобы мы получили её ID. ТЕБЕ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО СПРАШИВАТЬ КЛИЕНТА О ВРЕМЕНИ ДЛЯ ЗАПИСИ, КОНТАКТНЫХ ДАННЫХ ИЛИ ГОВОРИТЬ ЧТО ТЫ ЕГО ЗАПИСАЛ НА УСЛУГУ.
Твой главный источник данных: {context_section}
ИНСТРУКЦИЯ:
1.1 Если клиент просто выразил желание записаться или узнать услуги салона, вызови `GetCategories` и отправь полный список из инструмента.  
1.2 Если клиент сказал на какую услугу хочет записаться используй `FindService`.
1.3 Если Клиент хочет записаться к конкретному мастеру (называет имя и услугу) — используй `FindService` с указанием поля `master_name`. Если только имя — сначала уточни услугу.

ВАЖНО:
- Не придумывай услуги и цены. Бери только из инструментов. 
- Всегда вызывай инструмент с заполнение необходимых полей.
- Не пиши клиенту ID
- Сохраняй список нумерованным точо также как получаешь из инструмента.
- Узнать детали об услуге (в т.ч. кто из мастеров её делает - ViewServices)
- Если клиент решил сменить услугу или мастера - начинай сначала (не считая приветствия) по инструкции - вызывай инструменты снова.
"""
    
    return prompt


def service_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера услуг для выбора услуги в процессе бронирования
    
    Этот узел запускается, если service_id в состоянии бронирования все еще None.
    Использует инструменты GetCategories, GetServices, FindService
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
    
    # Получаем данные для контекста
    service_name = booking_state.get("service_name")
    master_id = booking_state.get("master_id")
    master_name = booking_state.get("master_name")
    
    # Формируем системный промпт с контекстом
    system_prompt = _build_system_prompt(
        service_id=service_id,
        service_name=service_name,
        master_id=master_id,
        master_name=master_name
    )
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    # Преобразуем messages в history для обратной совместимости
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
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем необходимые инструменты
        tools_registry.register_tool(GetCategories)
        tools_registry.register_tool(FindService)
        
        # Создаем orchestrator
        config = ResponsesAPIConfig()
        orchestrator = ResponsesOrchestrator(
            instructions=system_prompt,
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
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Service manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        
        return {
            "answer": reply,
            "used_tools": used_tools,
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в service_manager_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при выборе услуги. Попробуйте еще раз."
        }
