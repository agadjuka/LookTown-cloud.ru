"""
Узел менеджера консультаций об услугах для ответа на вопросы о содержании услуг
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, dicts_to_messages
from ..state import BookingSubState
from ..booking_state_updater import merge_booking_state
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструменты
from ....agents.tools.view_service.tool import ViewService
from ....agents.tools.masters.tool import Masters


def _build_system_prompt(service_name: Optional[str]) -> str:
    """
    Формирует системный промпт для узла about_service_manager в стиле консультанта
    
    Args:
        service_name: Название услуги (если есть)
        
    Returns:
        Системный промпт для LLM
    """    
    prompt = f"""Ты эксперт по услугам салона красоты LookTown. 
{context_section}
Твой стиль общения — дружелюбный, профессиональный, от женского лица, на "вы". 

ИНСТРУКЦИЯ: Тебе запрещено отвечать без использования инструментов, либо использовать свои знания вместо данных, полученных из инструментов.
   - если нужно получить информацию об услуге (цена, продолжительность, мастера и т.д.) используй `ViewService`.
   - если нужно получить информацию о мастерах салона используй `Masters`.
   - Если клиент интересуется квалификацией мастера, вызови `Masters` и отправь ему ссылку на страницу мастера из инструмента не придумывая своё описание мастера. Формулировка: "Все наши мастера работают под чутким руководством директора и отлично выполняют работу, можете ознакомиться с отзывами мастера: {{ссылка}}

После ответа на вопрос клиента ОБЯЗАТЕЛЬНО задай вовлекающий вопрос, чтобы вернуть клиента к записи:
   - Хотели бы записаться?"
"""
    
    return prompt


def about_service_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера консультаций об услугах для ответа на вопросы о содержании услуг
    
    Этот узел запускается, когда клиент хочет узнать подробности об услуге.
    Использует инструменты ViewService, Masters
    для консультации клиента об услугах и мастерах.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer и сброшенным флагом service_details_needed
    """
    logger.info("Запуск узла about_service_manager")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Получаем название услуги для контекста
    service_name = booking_state.get("service_name")
    
    # Формируем системный промпт
    system_prompt = _build_system_prompt(service_name=service_name)
    
    # Получаем сообщение пользователя и историю
    user_message = state.get("message", "")
    # Преобразуем messages в history для обратной совместимости
    messages = state.get("messages", [])
    history = messages_to_history(messages) if messages else []
    chat_id = state.get("chat_id")
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем необходимые инструменты
        tools_registry.register_tool(ViewService)
        tools_registry.register_tool(Masters)
        
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
        
        # Преобразуем новые сообщения из orchestrator в BaseMessage объекты
        new_messages_dicts = result.get("new_messages", [])
        new_messages = dicts_to_messages(new_messages_dicts) if new_messages_dicts else []
        
        # Проверяем, был ли вызван CallManager
        if result.get("call_manager"):
            logger.info("CallManager был вызван в about_service_manager_node")
            # Сбрасываем флаг service_details_needed даже при вызове CallManager
            updated_booking_state = merge_booking_state(booking_state, {"service_details_needed": False})
            updated_extracted_info = extracted_info.copy()
            updated_extracted_info["booking"] = updated_booking_state
            
            return {
                "messages": new_messages,
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "extracted_info": updated_extracted_info,
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # ВАЖНО: Сбрасываем флаг service_details_needed в False
        updated_booking_state = merge_booking_state(booking_state, {"service_details_needed": False})
        updated_extracted_info = extracted_info.copy()
        updated_extracted_info["booking"] = updated_booking_state
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"About service manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        logger.info("Флаг service_details_needed сброшен в False")
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
            "answer": reply,
            "extracted_info": updated_extracted_info,
            "used_tools": used_tools,
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в about_service_manager_node: {e}", exc_info=True)
        # Даже при ошибке сбрасываем флаг
        updated_booking_state = merge_booking_state(booking_state, {"service_details_needed": False})
        updated_extracted_info = extracted_info.copy()
        updated_extracted_info["booking"] = updated_booking_state
        
        return {
            "answer": "Извините, произошла ошибка при получении информации об услуге. Попробуйте еще раз.",
            "extracted_info": updated_extracted_info
        }

