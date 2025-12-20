"""
Узел менеджера слотов для предложения доступных временных слотов в процессе бронирования
"""
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент
from ....agents.tools.find_slots.tool import FindSlots


def slot_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера слотов для предложения доступных временных слотов
    
    Этот узел запускается, когда service_id уже есть, но slot_time еще не выбран.
    Использует инструмент FindSlots для поиска доступных слотов и предлагает их клиенту.
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer
    """
    logger.info("Запуск узла slot_manager")
    
    # Получаем текущее состояние бронирования
    extracted_info = state.get("extracted_info") or {}
    booking_state: Dict[str, Any] = extracted_info.get("booking", {})
    
    # Получаем service_id из состояния
    service_id = booking_state.get("service_id")
    if service_id is None:
        logger.error("slot_manager_node вызван без service_id - это ошибка логики графа")
        return {
            "answer": "Извините, произошла ошибка. Пожалуйста, начните бронирование заново."
        }
    
    # Получаем master_id (если есть)
    master_id = booking_state.get("master_id")
    master_name = booking_state.get("master_name")
    
    # Получаем пожелания по времени
    # Могут быть в slot_time (если это конкретное время) или в сообщении пользователя
    slot_time = booking_state.get("slot_time")
    user_message = state.get("message", "")
    
    # Формируем описание пожеланий по времени для промпта
    time_preference = _extract_time_preference(slot_time, user_message)
    
    # Формируем системный промпт согласно ТЗ
    system_prompt = _build_system_prompt(service_id, master_id, master_name, time_preference)
    
    # Получаем сообщение пользователя и историю
    history = state.get("history") or []
    chat_id = state.get("chat_id")
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем инструмент FindSlots
        tools_registry.register_tool(FindSlots)
        
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
            logger.info("CallManager был вызван в slot_manager_node")
            return {
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Slot manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        
        return {
            "answer": reply,
            "used_tools": used_tools,
            "tool_results": tool_calls if tool_calls else []
        }
        
    except Exception as e:
        logger.error(f"Ошибка в slot_manager_node: {e}", exc_info=True)
        return {
            "answer": "Извините, произошла ошибка при поиске доступного времени. Попробуйте еще раз."
        }


def _extract_time_preference(slot_time: Optional[str], user_message: str) -> str:
    """
    Извлекает пожелания по времени из slot_time или сообщения пользователя
    
    Args:
        slot_time: Конкретное время слота (если есть)
        user_message: Сообщение пользователя
        
    Returns:
        Строка с описанием пожеланий по времени для промпта
    """
    if slot_time:
        # Если есть конкретное время, преобразуем его в пожелание
        # Формат slot_time: "YYYY-MM-DD HH:MM"
        try:
            from datetime import datetime
            dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
            return f"Конкретная дата и время: {date_str} в {time_str}"
        except:
            return f"Конкретное время: {slot_time}"
    
    # Ищем пожелания в сообщении пользователя
    message_lower = user_message.lower()
    
    # Проверяем на упоминания времени суток
    if any(word in message_lower for word in ["утром", "утра", "утреннее"]):
        return "Утром"
    elif any(word in message_lower for word in ["днем", "днём", "дневное"]):
        return "Днем"
    elif any(word in message_lower for word in ["вечером", "вечер", "вечернее"]):
        return "Вечером"
    elif any(word in message_lower for word in ["после", "позже"]):
        # Пытаемся извлечь время после слова "после"
        import re
        after_match = re.search(r'после\s+(\d{1,2}):?(\d{2})?', message_lower)
        if after_match:
            hour = after_match.group(1)
            minute = after_match.group(2) or "00"
            return f"После {hour}:{minute}"
    elif any(word in message_lower for word in ["до", "раньше"]):
        # Пытаемся извлечь время после слова "до"
        import re
        before_match = re.search(r'до\s+(\d{1,2}):?(\d{2})?', message_lower)
        if before_match:
            hour = before_match.group(1)
            minute = before_match.group(2) or "00"
            return f"До {hour}:{minute}"
    
    # Проверяем на упоминания дат
    if any(word in message_lower for word in ["завтра", "tomorrow"]):
        return "Завтра"
    elif any(word in message_lower for word in ["послезавтра"]):
        return "Послезавтра"
    elif any(word in message_lower for word in ["сегодня", "today"]):
        return "Сегодня"
    
    return ""


def _build_system_prompt(
    service_id: int,
    master_id: Optional[int],
    master_name: Optional[str],
    time_preference: str
) -> str:
    """
    Формирует системный промпт для узла slot_manager согласно ТЗ
    
    Args:
        service_id: ID выбранной услуги
        master_id: ID мастера (если есть)
        master_name: Имя мастера (если есть)
        time_preference: Пожелания клиента по времени
        
    Returns:
        Системный промпт для LLM
    """
    # Формируем части контекста
    master_info = ""
    if master_id:
        master_info = f"{master_id}"
        if master_name:
            master_info += f" ({master_name})"
    elif master_name:
        master_info = master_name
    
    time_info = time_preference if time_preference else "не указаны"
    
    # Формируем инструкции по параметрам для FindSlots
    params_instructions = f"- service_id: ОБЯЗАТЕЛЬНО передай {service_id}\n"
    if master_id:
        params_instructions += f"- master_id: передай {master_id}\n"
    elif master_name:
        params_instructions += f"- master_name: передай '{master_name}'\n"
    
    if time_preference:
        # Преобразуем пожелания в формат для инструмента
        if "После" in time_preference and ":" in time_preference:
            # Извлекаем время после "После"
            time_part = time_preference.split("После")[1].strip()
            params_instructions += f"- time_period: передай 'after {time_part}'\n"
        elif "До" in time_preference and ":" in time_preference:
            # Извлекаем время после "До"
            time_part = time_preference.split("До")[1].strip()
            params_instructions += f"- time_period: передай 'before {time_part}'\n"
        elif "Утром" in time_preference:
            params_instructions += "- time_period: передай 'morning'\n"
        elif "Днем" in time_preference or "Днём" in time_preference:
            params_instructions += "- time_period: передай 'day'\n"
        elif "Вечером" in time_preference:
            params_instructions += "- time_period: передай 'evening'\n"
        elif "Завтра" in time_preference:
            from datetime import datetime, timedelta
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            params_instructions += f"- date: передай '{tomorrow}'\n"
        elif "Послезавтра" in time_preference:
            from datetime import datetime, timedelta
            day_after_tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            params_instructions += f"- date: передай '{day_after_tomorrow}'\n"
        elif "Сегодня" in time_preference:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            params_instructions += f"- date: передай '{today}'\n"
        elif "Конкретная дата" in time_preference or "Конкретное время" in time_preference:
            # Если есть конкретное время, извлекаем дату
            if ":" in time_preference:
                # Пытаемся извлечь дату из формата "YYYY-MM-DD"
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', time_preference)
                if date_match:
                    params_instructions += f"- date: передай '{date_match.group(1)}'\n"
    
    prompt = f"""Ты — AI-администратор салона LookTown. Сейчас этап подбора времени (слотов).
Твой стиль: дружелюбный, профессиональный, краткий.

КОНТЕКСТ:
- Выбранная услуга ID: {service_id}
- Выбранный мастер: {master_info if master_info else "не выбран"}
- Пожелания клиента по времени: {time_info}

ИНСТРУКЦИЯ (Шаг 2 из регламента):
2. Предложение доступных слотов.
   Клиент выбрал услугу. ОБЯЗАТЕЛЬНО используй инструмент `FindSlots` прямо сейчас.
   
ПАРАМЕТРЫ ДЛЯ FindSlots:
{params_instructions}
2.1 Если клиент указал пожелания (например, "вечером", "завтра", "после 18:00") — передай это в аргумент `time_period` или `date` инструмента `FindSlots`.
2.2 Если пожеланий нет — вызови `FindSlots` без строгих ограничений (на ближайшие дни), чтобы предложить варианты.

ВАЖНО:
- Не спрашивай "На какое время вас записать?", если ты еще не проверил доступность. Сначала вызови инструмент, получи слоты, и только потом выводи их клиенту.
- Если слотов нет, предложи ближайшие доступные или спроси про другой день.
- не задавай вопросов по мастерам и услугам, это не твоё дело.
"""
    
    return prompt

