"""
Orchestrator для обработки диалогов через OpenAI API
"""
import json
from typing import List, Dict, Any, Optional
from langchain_core.messages import trim_messages, BaseMessage
from .client import ResponsesAPIClient
from .tools_registry import ResponsesToolsRegistry
from .config import ResponsesAPIConfig
from ..logger_service import logger

# Импортируем CallManagerException один раз, а не в цикле
try:
    from ...agents.tools.call_manager import CallManagerException
except ImportError:
    CallManagerException = None


class ResponsesOrchestrator:
    """Orchestrator для обработки диалогов через OpenAI API"""
    
    def __init__(
        self,
        instructions: str,
        tools_registry: Optional[ResponsesToolsRegistry] = None,
        client: Optional[ResponsesAPIClient] = None,
        config: Optional[ResponsesAPIConfig] = None,
    ):
        """
        Инициализация orchestrator
        """
        self.instructions = instructions
        self.tools_registry = tools_registry or ResponsesToolsRegistry()
        self.config = config or ResponsesAPIConfig()
        self.client = client or ResponsesAPIClient(self.config)
    
    def run_turn(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Один полный ход диалога
        """
        # Получаем схемы инструментов один раз
        tools_schemas = self.tools_registry.get_all_tools_schemas()
        
        # Формируем messages для первого запроса к API
        # Включаем всю историю из PostgreSQL
        messages = []
        if history:
            for idx, msg in enumerate(history):
                try:
                    role = msg.get("role", "user")
                    
                    # Пропускаем system сообщения (например, "Tools used: ...", "EXTRACTED_INFO: ...")
                    if role == "system":
                        logger.debug(f"Пропущено system сообщение из истории: {str(msg.get('content', ''))[:100]}")
                        continue
                    
                    # Валидируем роль (включая обработку "final" и других недопустимых ролей)
                    valid_roles = ["user", "assistant", "tool"]
                    if role not in valid_roles:
                        # Маппинг недопустимых ролей
                        role_mapping = {
                            "final": "assistant",
                            "model": "assistant",
                            "ai": "assistant",
                            "bot": "assistant",
                        }
                        if role.lower() in role_mapping:
                            logger.warning(f"Обнаружена недопустимая роль '{role}' в истории (позиция {idx}), заменяем на '{role_mapping[role.lower()]}'")
                            role = role_mapping[role.lower()]
                            msg = msg.copy()
                            msg["role"] = role
                        else:
                            logger.warning(f"Обнаружен неожиданный role в истории: {role} (позиция {idx}), пропускаем сообщение")
                            continue
                
                    # Нормализуем сообщение для API
                    normalized_msg = {
                        "role": role,
                        "content": str(msg.get("content") or "")  # content должен быть строкой, не None
                    }
                    
                    # Если есть tool_calls, добавляем их (только если это assistant сообщение)
                    if role == "assistant" and msg.get("tool_calls"):
                        # Проверяем, что tool_calls в правильном формате
                        tool_calls = msg.get("tool_calls")
                        if isinstance(tool_calls, list) and tool_calls:
                            try:
                                # Пытаемся проверить, что это уже словари
                                if isinstance(tool_calls[0], dict):
                                    # Валидируем каждое tool_call
                                    valid_tool_calls = []
                                    for tc in tool_calls:
                                        if isinstance(tc, dict) and "id" in tc and "function" in tc:
                                            valid_tool_calls.append(tc)
                                        else:
                                            logger.warning(f"Пропущен невалидный tool_call в истории: {tc}")
                                    if valid_tool_calls:
                                        normalized_msg["tool_calls"] = valid_tool_calls
                                else:
                                    # Сериализуем объекты SDK в словари
                                    normalized_tool_calls = []
                                    for tc in tool_calls:
                                        try:
                                            tc_dict = {
                                                "id": str(tc.id if hasattr(tc, 'id') else tc.get("id", "")),
                                                "type": "function",
                                                "function": {
                                                    "name": str(tc.function.name if hasattr(tc, 'function') else tc.get("function", {}).get("name", "")),
                                                    "arguments": str(tc.function.arguments if hasattr(tc, 'function') else tc.get("function", {}).get("arguments", "{}"))
                                                }
                                            }
                                            normalized_tool_calls.append(tc_dict)
                                        except Exception as e:
                                            logger.warning(f"Ошибка при сериализации tool_call: {e}, пропускаем")
                                    if normalized_tool_calls:
                                        normalized_msg["tool_calls"] = normalized_tool_calls
                            except Exception as e:
                                logger.warning(f"Ошибка при обработке tool_calls из истории (позиция {idx}): {e}")
                                # Пропускаем tool_calls, если не удалось обработать
                    
                    # Если это tool сообщение, добавляем tool_call_id
                    if role == "tool":
                        tool_call_id = msg.get("tool_call_id")
                        if tool_call_id:
                            normalized_msg["tool_call_id"] = str(tool_call_id)
                        else:
                            # Пропускаем tool сообщения без tool_call_id
                            logger.debug(f"Пропущено tool сообщение без tool_call_id (позиция {idx})")
                            continue
                    
                    # Пропускаем пустые сообщения (кроме tool)
                    if role != "tool" and not normalized_msg.get("content") and not normalized_msg.get("tool_calls"):
                        logger.debug(f"Пропущено пустое сообщение (позиция {idx}, роль: {role})")
                        continue
                    
                    messages.append(normalized_msg)
                    
                except Exception as e:
                    logger.warning(f"Ошибка при обработке сообщения из истории (позиция {idx}): {e}, пропускаем")
                    continue
        
        # Если история пустая или последнее сообщение не совпадает с текущим,
        # добавляем текущее сообщение
        if not messages or messages[-1].get("content") != user_message:
            messages.append({
                "role": "user",
                "content": user_message
            })
        
        logger.debug(f"Отправка в API: {len(messages)} сообщений")
        
        # Цикл для обработки множественных вызовов инструментов
        max_iterations = 10
        iteration = 0
        tool_calls_info = []
        reply_text = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"Итерация {iteration}: Запрос к API")
            
            # Обрезаем историю перед вызовом LLM (оставляем последние 30 сообщений)
            # Используем trim_messages для правильной обрезки с сохранением системных сообщений
            try:
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
                
                # Преобразуем сообщения в объекты BaseMessage
                base_messages = []
                for msg in messages:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        base_messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        ai_msg = AIMessage(content=content)
                        # Добавляем tool_calls если есть
                        if msg.get("tool_calls"):
                            ai_msg.tool_calls = msg.get("tool_calls")
                        base_messages.append(ai_msg)
                    elif role == "tool":
                        tool_msg = ToolMessage(
                            content=content,
                            tool_call_id=msg.get("tool_call_id", "")
                        )
                        base_messages.append(tool_msg)
                    elif role == "system":
                        base_messages.append(SystemMessage(content=content))
                
                # Обрезаем историю: последние 30 сообщений, включая системные
                # Используем большой max_tokens, чтобы обрезка шла по количеству сообщений
                # trim_messages с strategy="last" оставит последние сообщения
                trimmed_messages = trim_messages(
                    base_messages,
                    max_tokens=100000,  # Большое значение, чтобы обрезка шла по количеству
                    strategy="last",
                    include_system=True,
                    allow_partial=False,
                )
                
                # Дополнительно ограничиваем до 30 сообщений (если trim_messages не сработал)
                if len(trimmed_messages) > 30:
                    # Сохраняем системные сообщения и берем последние 30 несистемных
                    system_msgs = [m for m in trimmed_messages if isinstance(m, SystemMessage)]
                    non_system_msgs = [m for m in trimmed_messages if not isinstance(m, SystemMessage)]
                    trimmed_messages = system_msgs + non_system_msgs[-30:]
                
                # Если обрезка произошла, логируем
                if len(trimmed_messages) < len(base_messages):
                    logger.info(f"История обрезана: {len(base_messages)} -> {len(trimmed_messages)} сообщений")
                
                # Преобразуем обратно в словари для API
                trimmed_dicts = []
                for msg in trimmed_messages:
                    msg_dict = {}
                    
                    # Обрабатываем разные типы сообщений
                    if isinstance(msg, HumanMessage):
                        msg_dict = {"role": "user", "content": msg.content}
                    elif isinstance(msg, AIMessage):
                        msg_dict = {"role": "assistant", "content": msg.content}
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            msg_dict["tool_calls"] = msg.tool_calls
                    elif isinstance(msg, ToolMessage):
                        msg_dict = {
                            "role": "tool",
                            "content": msg.content,
                            "tool_call_id": msg.tool_call_id
                        }
                    elif isinstance(msg, SystemMessage):
                        msg_dict = {"role": "system", "content": msg.content}
                    
                    if msg_dict:
                        trimmed_dicts.append(msg_dict)
                
                # Используем обрезанные сообщения
                messages_to_send = trimmed_dicts
                
            except Exception as e:
                logger.warning(f"Ошибка при обрезке истории: {e}, используем оригинальные сообщения")
                messages_to_send = messages
            
            # Запрос к модели
            try:
                response = self.client.create_response(
                    instructions=self.instructions,
                    input_messages=messages_to_send,  # Передаем обрезанные сообщения
                    tools=tools_schemas if tools_schemas else None,
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе к API на итерации {iteration}: {e}", exc_info=True)
                # Если это первая итерация и произошла ошибка, возвращаем сообщение об ошибке
                if iteration == 1:
                    error_message = "Извините, произошла техническая ошибка. Пожалуйста, попробуйте еще раз через несколько секунд."
                    return {
                        "reply": error_message,
                        "tool_calls": tool_calls_info,
                        "raw_response": None,
                    }
                break
            
            message = response.choices[0].message
            
            # Добавляем ответ ассистента в историю сообщений
            # Важно: правильно сериализуем tool_calls из объекта SDK в словари
            assistant_msg = {
                "role": "assistant",
                "content": message.content or ""  # content должен быть строкой, не None
            }
            
            # Правильно сериализуем tool_calls из объекта SDK в формат словарей
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            
            messages.append(assistant_msg)
            
            # Проверяем tool_calls
            if message.tool_calls:
                logger.debug(f"Найдено {len(message.tool_calls)} вызовов инструментов на итерации {iteration}")
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    call_id = tool_call.id
                    args_json = tool_call.function.arguments
                    
                    try:
                        args = json.loads(args_json)
                    except json.JSONDecodeError:
                        logger.error(f"Ошибка парсинга аргументов для {func_name}: {args_json}")
                        args = {}
                    
                    logger.info(f"🔧 Использован инструмент: {func_name}")
                    logger.info(f"📋 Аргументы: {json.dumps(args, ensure_ascii=False, indent=2)}")
                    
                    try:
                        result = self.tools_registry.call_tool(func_name, args, conversation_history=None, chat_id=chat_id)
                        
                        tool_call_info = {
                            "name": func_name,
                            "call_id": call_id,
                            "args": args,
                            "result": result,
                        }
                        tool_calls_info.append(tool_call_info)
                        
                        # Добавляем результат в сообщения
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                        })
                        
                    except Exception as e:
                        # Проверяем CallManager
                        if CallManagerException and isinstance(e, CallManagerException):
                            escalation_result = e.escalation_result
                            logger.info(f"CallManager вызван через инструмент {func_name}")
                            
                            return {
                                "reply": escalation_result.get("user_message"),
                                "tool_calls": tool_calls_info,
                                "call_manager": True,
                                "manager_alert": escalation_result.get("manager_alert"),
                            }
                        
                        logger.error(f"Ошибка при вызове инструмента {func_name}: {e}", exc_info=True)
                        error_result = f"Ошибка при выполнении инструмента: {str(e)}"
                        
                        tool_call_info = {
                            "name": func_name,
                            "call_id": call_id,
                            "args": args,
                            "result": error_result,
                        }
                        tool_calls_info.append(tool_call_info)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": error_result
                        })
                
                # Продолжаем цикл, чтобы модель могла ответить на результаты инструментов
                continue
            
            # Если нет tool_calls, значит это финальный ответ
            if message.content:
                reply_text = message.content
                logger.info(f"Получен текстовый ответ на итерации {iteration} (длина: {len(reply_text)})")
                break
            else:
                logger.warning(f"Пустой ответ от модели на итерации {iteration}")
                break
        
        if iteration >= max_iterations:
            logger.warning(f"Достигнут лимит итераций ({max_iterations}). Прекращаем цикл.")
        
        # Если ответ пустой, возвращаем сообщение об ошибке
        if not reply_text or not reply_text.strip():
            logger.warning("Получен пустой ответ от API")
            reply_text = "Извините, не удалось получить ответ. Пожалуйста, попробуйте еще раз."
        
        return {
            "reply": reply_text,
            "tool_calls": tool_calls_info,
            "raw_response": response if 'response' in locals() else None,
        }
