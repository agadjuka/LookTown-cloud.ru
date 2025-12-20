"""
Узлы подграфа бронирования
"""
from .service_manager import service_manager_node
from .slot_manager import slot_manager_node

__all__ = [
    "service_manager_node",
    "slot_manager_node",
]
