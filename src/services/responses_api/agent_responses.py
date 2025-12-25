"""
Пример использования Responses API для агента

ВНИМАНИЕ: Этот файл содержит пример использования Responses API.
В реальном проекте агенты создаются через BaseAgent, который сам создает ResponsesOrchestrator.
Этот файл оставлен для документации и примеров использования.
"""
import os
from typing import List, Dict, Any, Optional

from .client import ResponsesAPIClient
from .orchestrator import ResponsesOrchestrator
from .tools_registry import ResponsesToolsRegistry
from .config import ResponsesAPIConfig

# Импортируем все инструменты
from ...agents.tools import (
    GetCategories,
    FindSlots,
    CreateBooking,
    ViewService,
    FindService,
    GetClientRecords,
    CancelBooking,
    RescheduleBooking,
    CallManager,
    Masters,
)


# Инструкции ассистента
ASSISTANT_INSTRUCTIONS = """
You are an AI administrator of the LookTown beauty salon.

Communicate briefly, to the point, friendly, like a live administrator in a messenger.

Always clarify booking details (service, master, date, time), use functions
to check slots and create bookings in CRM. Do not make up non-existent slots.
"""


def create_responses_agent() -> ResponsesOrchestrator:
    """
    Создание настроенного агента с Responses API
    
    Returns:
        Настроенный ResponsesOrchestrator
    """
    # Создаём конфигурацию
    config = ResponsesAPIConfig()
    
    # Создаём регистрацию инструментов
    tools_registry = ResponsesToolsRegistry()
    
    # Регистрируем все инструменты
    all_tools = [
        GetCategories,
        FindSlots,
        CreateBooking,
        ViewService,
        FindService,
        GetClientRecords,
        CancelBooking,
        RescheduleBooking,
        CallManager,
        Masters,
    ]
    
    tools_registry.register_tools_from_list(all_tools)
    
    # Создаём orchestrator с конфигурацией
    orchestrator = ResponsesOrchestrator(
        instructions=ASSISTANT_INSTRUCTIONS,
        tools_registry=tools_registry,
        config=config
    )
    
    return orchestrator


def run_agent_turn(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Один полный ход диалога (удобная обёртка)
    
    Args:
        user_message: Сообщение пользователя
        conversation_history: История диалога
        
    Returns:
        Словарь с reply и conversation_history
    """
    orchestrator = create_responses_agent()
    return orchestrator.run_turn(user_message, conversation_history)


# Пример использования
if __name__ == "__main__":
    """
    Пример локального запуска: можно дергать из Telegram-бота.
    В реальном боте conversation_history надо хранить по user_id / chat_id.
    """
    history: Optional[List[Dict[str, Any]]] = []
    print("AI-администратор (Responses API). Напишите 'exit' для выхода.")
    
    while True:
        user_input = input("Вы: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        
        result = run_agent_turn(user_input, history)
        history = result["conversation_history"]
        print("Бот:", result["reply"])
        
        # Показываем вызовы инструментов если были
        if result.get("tool_calls"):
            print("\n🔧 Использованные инструменты:")
            for tool_call in result["tool_calls"]:
                print(f"  - {tool_call['name']}")

