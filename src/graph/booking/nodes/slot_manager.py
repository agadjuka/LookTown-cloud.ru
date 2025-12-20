"""
Узел менеджера слотов для предложения доступных временных слотов в процессе бронирования
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ..state import BookingSubState
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент и логику
from ....agents.tools.find_slots.tool import FindSlots
from ....agents.tools.find_slots.logic import find_slots_by_period
from ....agents.tools.common.yclients_service import YclientsService


def slot_manager_node(state: ConversationState) -> ConversationState:
    """
    Узел менеджера слотов для предложения доступных временных слотов
    
    Этот узел запускается в двух случаях:
    1. Когда service_id есть, но slot_time еще не выбран - ищет и предлагает слоты
    2. Когда slot_time указан, но не проверен - проверяет доступность времени
    
    Args:
        state: Текущее состояние графа диалога
        
    Returns:
        Обновленное состояние с ответом в поле answer (или пустым, если время проверено)
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
    
    # Получаем slot_time и проверяем, нужно ли его проверить
    slot_time = booking_state.get("slot_time")
    slot_time_verified = booking_state.get("slot_time_verified", False)
    
    # Если slot_time указан, но не проверен - проверяем его доступность
    if slot_time and not slot_time_verified:
        logger.info(f"Проверка доступности указанного времени: {slot_time}")
        return _verify_slot_time_availability(state, booking_state, service_id, slot_time)
    
    # Иначе - обычная логика: ищем и предлагаем слоты
    return _find_and_offer_slots(state, booking_state, service_id)


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


def _verify_slot_time_availability(
    state: ConversationState,
    booking_state: Dict[str, Any],
    service_id: int,
    slot_time: str
) -> ConversationState:
    """
    Проверяет доступность указанного времени слота
    
    Args:
        state: Текущее состояние диалога
        booking_state: Состояние бронирования
        service_id: ID услуги
        slot_time: Время слота в формате "YYYY-MM-DD HH:MM"
        
    Returns:
        Обновленное состояние с результатом проверки
    """
    try:
        # Парсим время
        try:
            dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
        except ValueError:
            logger.error(f"Неверный формат slot_time: {slot_time}")
            # Сбрасываем некорректное время
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time"] = None
            updated_booking_state["slot_time_verified"] = None
            return {
                "extracted_info": {
                    **state.get("extracted_info", {}),
                    "booking": updated_booking_state
                },
                "answer": "Извините, произошла ошибка с указанным временем. Давайте выберем другое время."
            }
        
        # Получаем параметры мастера
        master_id = booking_state.get("master_id")
        master_name = booking_state.get("master_name")
        
        # Проверяем доступность через FindSlots
        try:
            yclients_service = YclientsService()
        except ValueError as e:
            logger.error(f"Ошибка конфигурации YclientsService: {e}")
            # Сбрасываем время при ошибке конфигурации
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time"] = None
            updated_booking_state["slot_time_verified"] = None
            return {
                "extracted_info": {
                    **state.get("extracted_info", {}),
                    "booking": updated_booking_state
                },
                "answer": "Извините, произошла ошибка при проверке доступности времени. Попробуйте еще раз."
            }
        
        # Вызываем find_slots_by_period для проверки конкретного времени
        result = asyncio.run(
            find_slots_by_period(
                yclients_service=yclients_service,
                service_id=service_id,
                time_period=time_str,  # Конкретное время для проверки
                master_name=master_name,
                master_id=master_id,
                date=date_str
            )
        )
        
        if result.get('error'):
            logger.warning(f"Ошибка при проверке доступности времени: {result['error']}")
            # Если ошибка - сбрасываем время и предлагаем выбрать другое
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time"] = None
            updated_booking_state["slot_time_verified"] = None
            return {
                "extracted_info": {
                    **state.get("extracted_info", {}),
                    "booking": updated_booking_state
                },
                "answer": f"К сожалению, время {time_str} на {date_str} недоступно. Давайте выберем другое время?"
            }
        
        # Проверяем, есть ли это время в результатах
        results = result.get('results', [])
        time_found = False
        
        # Преобразуем время в минуты для проверки
        def time_to_minutes(time_str: str) -> int:
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        
        target_minutes = time_to_minutes(time_str)
        
        for day_result in results:
            if day_result.get('date') == date_str:
                slots = day_result.get('slots', [])
                # Проверяем, есть ли нужное время в слотах
                for slot in slots:
                    # Слот может быть в формате "HH:MM" или "HH:MM-HH:MM"
                    if '-' in slot:
                        # Интервал: проверяем, попадает ли время в интервал
                        parts = slot.split('-')
                        start_time = parts[0].strip()
                        end_time = parts[1].strip() if len(parts) > 1 else start_time
                        start_minutes = time_to_minutes(start_time)
                        end_minutes = time_to_minutes(end_time)
                        # Время доступно, если оно попадает в интервал (включительно начало, исключительно конец)
                        if start_minutes <= target_minutes < end_minutes:
                            time_found = True
                            break
                    else:
                        # Отдельное время: точное совпадение
                        if slot == time_str:
                            time_found = True
                            break
                if time_found:
                    break
        
        if time_found:
            # Время доступно - устанавливаем флаг и возвращаем пустой answer
            logger.info(f"Время {slot_time} доступно, устанавливаем slot_time_verified=True")
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time_verified"] = True
            return {
                "extracted_info": {
                    **state.get("extracted_info", {}),
                    "booking": updated_booking_state
                },
                "answer": ""  # Пустой ответ - не пишем клиенту
            }
        else:
            # Время недоступно - сообщаем клиенту и сбрасываем
            logger.info(f"Время {slot_time} недоступно")
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time"] = None
            updated_booking_state["slot_time_verified"] = None
            
            # Форматируем дату для сообщения
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
            except:
                formatted_date = date_str
            
            return {
                "extracted_info": {
                    **state.get("extracted_info", {}),
                    "booking": updated_booking_state
                },
                "answer": f"К сожалению, время {time_str} на {formatted_date} недоступно. Давайте выберем другое время."
            }
            
    except Exception as e:
        logger.error(f"Ошибка при проверке доступности времени: {e}", exc_info=True)
        # При ошибке сбрасываем время
        updated_booking_state = booking_state.copy()
        updated_booking_state["slot_time"] = None
        updated_booking_state["slot_time_verified"] = None
        return {
            "extracted_info": {
                **state.get("extracted_info", {}),
                "booking": updated_booking_state
            },
            "answer": "Извините, произошла ошибка при проверке доступности времени. Давайте выберем другое время?"
        }


def _find_and_offer_slots(
    state: ConversationState,
    booking_state: Dict[str, Any],
    service_id: int
) -> ConversationState:
    """
    Ищет и предлагает доступные слоты клиенту (обычная логика работы slot_manager)
    
    Args:
        state: Текущее состояние диалога
        booking_state: Состояние бронирования
        service_id: ID услуги
        
    Returns:
        Обновленное состояние с ответом и предложенными слотами
    """
    # Получаем master_id (если есть)
    master_id = booking_state.get("master_id")
    master_name = booking_state.get("master_name")
    
    # Получаем пожелания по времени из сообщения пользователя
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
ТЕБЕ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО СПРАШИВАТЬ КЛИЕНТА О ЖЕЛАЕМОЙ УСЛУГЕ, КОНТАКТНЫХ ДАННЫХ ИЛИ ГОВОРИТЬ ЧТО ТЫ ЕГО ЗАПИСАЛ НА УСЛУГУ.

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
- Не задавай вопросов по мастерам и услугам, это не твоё дело.
- FindSlots автоматически получает слоты на 3 дня вперед, не нужно спрашивать клиента о конкретной дате.

"""
    
    return prompt

