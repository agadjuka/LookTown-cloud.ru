"""
Узел менеджера слотов для предложения доступных временных слотов в процессе бронирования
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from ...conversation_state import ConversationState
from ...utils import messages_to_history, dicts_to_messages, filter_history_conversation_only
from ..state import BookingSubState
from ..booking_state_updater import try_update_booking_state_from_reply
from ....services.responses_api.orchestrator import ResponsesOrchestrator
from ....services.responses_api.tools_registry import ResponsesToolsRegistry
from ....services.responses_api.config import ResponsesAPIConfig
from ....services.logger_service import logger

# Импортируем инструмент и логику
from ....agents.tools.find_slots.tool import FindSlots
from ....agents.tools.find_slots.logic import find_slots_by_period
from ....agents.tools.common.yclients_service import YclientsService
from ....agents.tools.call_manager import CallManager


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
    # ВАЖНО: Если время 00:00, это не считается выбранным временем, обрабатываем как дату без времени
    if slot_time and not slot_time_verified:
        if _is_midnight_time(slot_time):
            logger.info(f"Обнаружено время 00:00 в slot_time={slot_time}, обрабатываем как дату без времени")
            # Сбрасываем slot_time, чтобы slot_manager искал слоты на эту дату
            updated_booking_state = booking_state.copy()
            updated_booking_state["slot_time"] = None
            updated_booking_state["slot_time_verified"] = None
            # Продолжаем с поиском слотов на эту дату
            return _find_and_offer_slots(
                {
                    **state,
                    "extracted_info": {
                        **state.get("extracted_info", {}),
                        "booking": updated_booking_state
                    }
                },
                updated_booking_state,
                service_id
            )
        logger.info(f"Проверка доступности указанного времени: {slot_time}")
        return _verify_slot_time_availability(state, booking_state, service_id, slot_time)
    
    # Иначе - обычная логика: ищем и предлагаем слоты
    return _find_and_offer_slots(state, booking_state, service_id)


def _is_midnight_time(slot_time: str) -> bool:
    """
    Проверяет, является ли время в slot_time полночью (00:00)
    
    Args:
        slot_time: Время в формате "YYYY-MM-DD HH:MM"
        
    Returns:
        True, если время равно 00:00, иначе False
    """
    try:
        dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
        return dt.hour == 0 and dt.minute == 0
    except (ValueError, AttributeError):
        return False


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
        # ВАЖНО: Если время 00:00, это не считается выбранным временем
        if _is_midnight_time(slot_time):
            # Обрабатываем как дату без времени
            try:
                dt = datetime.strptime(slot_time, "%Y-%m-%d %H:%M")
                date_str = dt.strftime("%Y-%m-%d")
                return f"Конкретная дата: {date_str}"
            except:
                return ""
        try:
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
        # Структура результата: {"masters": [{"results": [{"date": ..., "slots": [...]}]}]}
        masters = result.get('masters', [])
        time_found = False
        
        # Преобразуем время в минуты для проверки
        def time_to_minutes(time_str: str) -> int:
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        
        target_minutes = time_to_minutes(time_str)
        
        # Проверяем результаты для каждого мастера
        for master_data in masters:
            # Если указан конкретный мастер, проверяем соответствие
            if master_id:
                result_master_id = master_data.get('master_id')
                if result_master_id != master_id:
                    continue
            elif master_name:
                result_master_name = master_data.get('master_name')
                if result_master_name and result_master_name.lower() != master_name.lower():
                    continue
            
            master_results = master_data.get('results', [])
            for day_result in master_results:
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
    # Фильтруем историю: оставляем только переписку (user и assistant), без tool messages
    messages = state.get("messages", [])
    history = filter_history_conversation_only(messages) if messages else []
    chat_id = state.get("chat_id")
    
    try:
        # Создаем регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        
        # Регистрируем инструмент FindSlots
        tools_registry.register_tool(FindSlots)
        tools_registry.register_tool(CallManager)
        
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
            logger.info("CallManager был вызван в slot_manager_node")
            return {
                "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения
                "answer": result.get("reply", ""),
                "manager_alert": result.get("manager_alert"),
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Получаем текущее состояние для проверки JSON
        extracted_info = state.get("extracted_info") or {}
        booking_state_current = extracted_info.get("booking", {})
        
        # Проверяем, есть ли JSON в ответе для обновления состояния
        updated_extracted_info = try_update_booking_state_from_reply(
            reply=reply,
            current_booking_state=booking_state_current,
            extracted_info=extracted_info
        )
        
        # Если JSON найден и состояние обновлено - не отправляем сообщение клиенту
        if updated_extracted_info:
            logger.info("JSON найден в ответе slot_manager, состояние обновлено, пропускаем отправку сообщения клиенту")
            return {
                "messages": new_messages,
                "answer": "",  # Пустой answer - процесс продолжается автоматически
                "extracted_info": updated_extracted_info,
                "used_tools": [tc.get("name") for tc in tool_calls] if tool_calls else [],
                "tool_results": tool_calls if tool_calls else []
            }
        
        # Формируем список использованных инструментов
        used_tools = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        logger.info(f"Slot manager ответил: {reply[:100]}...")
        logger.info(f"Использованные инструменты: {used_tools}")
        
        return {
            "messages": new_messages,  # КРИТИЧНО: Возвращаем все новые сообщения (AIMessage с tool_calls и ToolMessage)
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
    params_instructions = f"- service_id: MANDATORY pass {service_id}\n"
    if master_id:
        params_instructions += f"- master_id: pass {master_id}\n"
    elif master_name:
        params_instructions += f"- master_name: pass '{master_name}'\n"
    
    if time_preference:
        # Преобразуем пожелания в формат для инструмента
        if "После" in time_preference and ":" in time_preference:
            # Извлекаем время после "После"
            time_part = time_preference.split("После")[1].strip()
            params_instructions += f"- time_period: pass 'after {time_part}'\n"
        elif "До" in time_preference and ":" in time_preference:
            # Извлекаем время после "До"
            time_part = time_preference.split("До")[1].strip()
            params_instructions += f"- time_period: pass 'before {time_part}'\n"
        elif "Утром" in time_preference:
            params_instructions += "- time_period: pass 'morning'\n"
        elif "Днем" in time_preference or "Днём" in time_preference:
            params_instructions += "- time_period: pass 'day'\n"
        elif "Вечером" in time_preference:
            params_instructions += "- time_period: pass 'evening'\n"
        elif "Завтра" in time_preference:
            from datetime import datetime, timedelta
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            params_instructions += f"- date: pass '{tomorrow}'\n"
        elif "Послезавтра" in time_preference:
            from datetime import datetime, timedelta
            day_after_tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            params_instructions += f"- date: pass '{day_after_tomorrow}'\n"
        elif "Сегодня" in time_preference:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            params_instructions += f"- date: pass '{today}'\n"
        elif "Конкретная дата" in time_preference or "Конкретное время" in time_preference:
            # Если есть конкретное время, извлекаем дату
            if ":" in time_preference:
                # Пытаемся извлечь дату из формата "YYYY-MM-DD"
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', time_preference)
                if date_match:
                    params_instructions += f"- date: pass '{date_match.group(1)}'\n"
    
    prompt = f"""You are an AI administrator of the LookTown beauty salon. Currently at the service selection stage.
Your communication style is friendly, professional, brief. Address clients with "вы" (formal you), from a female perspective.
YOU ARE STRICTLY FORBIDDEN TO ASK THE CLIENT ABOUT THE DESIRED SERVICE, CONTACT DETAILS OR SAY THAT YOU BOOKED THEM FOR A SERVICE.
YOU ARE STRICTLY FORBIDDEN TO MAKE UP AVAILABLE SLOTS, TAKE THEM ONLY FROM THE `FindSlots` TOOL.

CONTEXT:
- Selected service ID: {service_id}
- Selected master: {master_info if master_info else "не выбран"}
- Client's time preferences: {time_info}

   The client has chosen a service. MANDATORY use the `FindSlots` tool right now, write to them strictly the output from the tool without changing the wording.
   
PARAMETERS FOR FindSlots:
{params_instructions}
1 If the client specified preferences (e.g., "вечером", "завтра", "после 18:00") — pass this to the `time_period` or `date` argument of the `FindSlots` tool.
2 If there are no preferences — call `FindSlots` without strict restrictions (for the nearest days) to offer options.
3 If the client chose a slot (including if they named a master who has only one available slot, return ONLY JSON with the service time in the format:  {{"slot_time": "YYYY-MM-DD HH:MM"}}  NEVER SEND {{"service_id": }}
If there are no available slots, tell the client about it, suggest selecting other slots or time. NEVER MAKE UP AVAILABLE SLOTS, TAKE THEM ONLY FROM THE `FindSlots` TOOL.
If you encounter a system error, don't know the answer to a question, or the client is dissatisfied - call the manager (if you already called the manager, don't call it again, continue the conversation).
 (if you already called the manager, don't call it again, continue the conversation).
"""
    
    return prompt

