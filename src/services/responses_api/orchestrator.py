"""
Orchestrator для обработки диалогов через OpenAI API
"""
import json
from typing import List, Dict, Any, Optional
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
            for msg in history:
                # Пропускаем system сообщения (например, "Tools used: ...")
                if msg.get("role") == "system":
                    continue
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
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
            
            # Запрос к модели
            try:
                response = self.client.create_response(
                    instructions=self.instructions,
                    input_messages=messages, # Передаем накопленные сообщения
                    tools=tools_schemas if tools_schemas else None,
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе к API на итерации {iteration}: {e}", exc_info=True)
                break
            
            message = response.choices[0].message
            
            # Добавляем ответ ассистента в историю сообщений
            # Важно: для OpenAI нужно добавлять объект message целиком или корректный словарь
            assistant_msg = {
                "role": "assistant",
                "content": message.content
            }
            if message.tool_calls:
                assistant_msg["tool_calls"] = message.tool_calls
            
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
        
        return {
            "reply": reply_text,
            "tool_calls": tool_calls_info,
            "raw_response": response if 'response' in locals() else None,
        }
