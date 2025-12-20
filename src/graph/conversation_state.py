"""
Состояние для основного графа диалога (Responses API)
"""
from typing import TypedDict, Optional, List, Dict, Any


class ConversationState(TypedDict):
    """Состояние основного графа диалога"""
    message: str                                    # Исходное сообщение пользователя
    chat_id: Optional[str]                         # ID чата в Telegram
    conversation_id: Optional[str]                 # ID диалога в PostgreSQL
    history: Optional[List[Dict[str, Any]]]       # История сообщений из PostgreSQL
    stage: Optional[str]                           # Определённая стадия диалога
    extracted_info: Optional[dict]                 # Извлечённая информация
    answer: str                                    # Финальный ответ пользователю
    manager_alert: Optional[str]                   # Сообщение для менеджера (если нужно)
    agent_name: Optional[str]                      # Имя агента, который дал ответ
    used_tools: Optional[list]                    # Список использованных инструментов
    tool_results: Optional[List[Dict[str, Any]]]  # Полная информация о результатах инструментов

