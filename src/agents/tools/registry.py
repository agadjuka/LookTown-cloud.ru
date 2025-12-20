"""
Реестр инструментов для управления списком доступных инструментов.

Этот реестр используется эдитором для получения списка всех инструментов.
При создании нового инструмента он автоматически обнаруживается из __init__.py.
"""

from typing import Dict, List, Optional, Type
from pydantic import BaseModel


class ToolsRegistry:
    """Реестр инструментов."""
    
    def __init__(self):
        """Инициализация реестра."""
        self._tools: Dict[str, Type[BaseModel]] = {}
        self._load_tools()
    
    def _load_tools(self) -> None:
        """Загружает все инструменты из модулей."""
        try:
            # Импортируем все инструменты напрямую из tool.py, минуя __init__.py
            # чтобы избежать циклических импортов через src.agents.__init__.py
            from .get_categories.tool import GetCategories
            from .get_services.tool import GetServices
            from .find_slots.tool import FindSlots
            from .create_booking.tool import CreateBooking
            from .view_service.tool import ViewService
            from .get_client_records.tool import GetClientRecords
            from .cancel_booking.tool import CancelBooking
            from .reschedule_booking.tool import RescheduleBooking
            from .call_manager.tool import CallManager
            from .about_salon.tool import AboutSalon
            from .masters.tool import Masters
            from .greet.tool import Greet
            from .find_service.tool import FindService
            
            # Регистрируем все инструменты
            tools_list = [
                GetCategories,
                GetServices,
                FindSlots,
                CreateBooking,
                ViewService,
                GetClientRecords,
                CancelBooking,
                RescheduleBooking,
                CallManager,
                AboutSalon,
                Masters,
                Greet,
                FindService,
            ]
            
            for tool_class in tools_list:
                # Проверяем, что это класс BaseModel с методом process
                if (isinstance(tool_class, type) and 
                    issubclass(tool_class, BaseModel) and
                    hasattr(tool_class, 'process') and
                    callable(getattr(tool_class, 'process'))):
                    self._tools[tool_class.__name__] = tool_class
                
        except ImportError as e:
            # Если инструменты еще не импортированы, реестр будет пустым
            # Это нормально при первой инициализации
            print(f"[WARNING] Ошибка импорта инструментов: {e}")
        except Exception as e:
            print(f"[WARNING] Ошибка при загрузке инструментов: {e}")
    
    def get_tool(self, name: str) -> Optional[Type[BaseModel]]:
        """
        Получить инструмент по имени.
        
        Args:
            name: Имя инструмента
            
        Returns:
            Класс инструмента или None
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[Type[BaseModel]]:
        """
        Получить список всех зарегистрированных инструментов.
        
        Returns:
            Список всех классов инструментов
        """
        return list(self._tools.values())
    
    def get_tool_names(self) -> List[str]:
        """
        Получить список имен всех инструментов.
        
        Returns:
            Список имен инструментов
        """
        return list(self._tools.keys())


# Глобальный экземпляр реестра
_registry: Optional[ToolsRegistry] = None


def get_registry() -> ToolsRegistry:
    """
    Получить глобальный экземпляр реестра.
    
    Returns:
        Экземпляр реестра инструментов
    """
    global _registry
    if _registry is None:
        _registry = ToolsRegistry()
    return _registry
