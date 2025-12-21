"""
Базовый класс для агентов (Responses API)
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from ..services.responses_api.orchestrator import ResponsesOrchestrator
from ..services.responses_api.tools_registry import ResponsesToolsRegistry
from ..services.logger_service import logger
from ..services.llm_request_logger import llm_request_logger
from ..services.tool_history_service import get_tool_history_service


class BaseAgent:
    """Базовый класс для всех агентов (использует Responses API)"""
    
    def __init__(
        self,
        langgraph_service,
        instruction: str,
        tools: list = None,
        agent_name: str = None
    ):
        self.langgraph_service = langgraph_service
        self.instruction = instruction
        self.agent_name = agent_name or self.__class__.__name__
        
        # Сохраняем классы инструментов для вызова
        if tools:
            self.tools = {x.__name__: x for x in tools}
        else:
            self.tools = {}
        
        # Создаём регистрацию инструментов
        tools_registry = ResponsesToolsRegistry()
        if tools:
            tools_registry.register_tools_from_list(tools)
        
        # Используем конфигурацию из langgraph_service для избежания дублирования
        from ..services.responses_api.config import ResponsesAPIConfig
        config = langgraph_service.config if hasattr(langgraph_service, 'config') else ResponsesAPIConfig()
        
        # Создаём orchestrator с общей конфигурацией
        self.orchestrator = ResponsesOrchestrator(
            instructions=instruction,
            tools_registry=tools_registry,
            config=config,
            )
        
        # Инициализируем список для отслеживания tool_calls
        self._last_tool_calls = []
        
        # Результат CallManager (если был вызван)
        self._call_manager_result = None
        
        # КРИТИЧНО: Сохраняем новые сообщения из orchestrator для передачи в LangGraph
        self._last_new_messages = []
        
    def __call__(self, message: str, history: Optional[List[Dict[str, Any]]] = None, chat_id: Optional[str] = None) -> str:
        """
        Выполнение запроса к агенту
        
        :param message: Сообщение для агента
        :param history: История сообщений (преобразованная из LangGraph messages)
        :param chat_id: ID чата в Telegram (для передачи в инструменты)
        :return: Ответ агента
        """
        try:
            # Очищаем предыдущие tool_calls и сообщения
            self._last_tool_calls = []
            self._call_manager_result = None
            self._last_new_messages = []
            
            # Логируем сообщение пользователя
            llm_request_logger.start_new_request()
            timestamp = datetime.now().isoformat()
            log_entry = f"\n{'='*80}\n"
            log_entry += f"[{timestamp}] USER MESSAGE (EXACT DATA SENT TO API)\n"
            log_entry += f"{'='*80}\n"
            log_entry += f"Agent: {self.agent_name}\n"
            log_entry += f"Message:\n{message}\n"
            log_entry += f"History: {len(history) if history else 0} messages\n"
            llm_request_logger._write_raw(log_entry)
            
            # Логируем запрос к LLM
            llm_request_logger.log_request_to_llm(
                agent_name=self.agent_name,
                thread_id=None,
                assistant_id=None,
                instruction=self.instruction,
                tools=list(self.tools.values()),
                messages=history  # Передаём историю для логирования
            )
            
            # Выполняем запрос через orchestrator
            result = self.orchestrator.run_turn(message, history, chat_id=chat_id)
            
            # КРИТИЧНО: Сохраняем все новые сообщения из orchestrator (включая AIMessage с tool_calls и ToolMessage)
            new_messages_dicts = result.get("new_messages", [])
            if new_messages_dicts:
                # Преобразуем в формат LangGraph
                from ..graph.utils import orchestrator_messages_to_langgraph
                self._last_new_messages = orchestrator_messages_to_langgraph(new_messages_dicts)
            
            # Сохраняем tool_calls
            if result.get("tool_calls"):
                self._last_tool_calls = result["tool_calls"]
            
            # Проверяем CallManager
            if result.get("call_manager"):
                self._call_manager_result = {
                    "user_message": result.get("reply", ""),
                    "manager_alert": result.get("manager_alert"),
                }
                return "[CALL_MANAGER_RESULT]"
            
            reply = result.get("reply", "")
            raw_response = result.get("raw_response")
                    
            # Логируем ответ от LLM
            llm_request_logger.log_response_from_llm(
                agent_name=self.agent_name,
                response_text=reply,
                tool_calls=self._last_tool_calls if self._last_tool_calls else None,
                raw_response=raw_response
            )
                
            return reply
        
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            
            # Логируем ошибку в LLM лог
            try:
                llm_request_logger.log_error(
                    agent_name=self.agent_name,
                    error=e,
                    context=f"Message: {message[:200]}"
                )
            except Exception as log_error:
                logger.debug(f"Ошибка при логировании ошибки: {log_error}")
            
            logger.error(f"Ошибка в агенте {self.agent_name}: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            logger.error(f"Сообщение агента: {message[:200]}")
            logger.error(f"Traceback:\n{error_traceback}")
            raise
