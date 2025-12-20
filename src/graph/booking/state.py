"""
Состояние для подграфа бронирования (Booking Subgraph)
"""
from typing import TypedDict, Optional
from enum import Enum


class DialogStep(str, Enum):
    """Шаги диалога бронирования"""
    SERVICE = "service"
    SLOT = "slot"
    CONTACTS = "contacts"
    CONFIRMATION = "confirmation"


class BookingSubState(TypedDict, total=False):
    """Состояние подграфа бронирования"""
    service_id: Optional[int]              # ID услуги
    service_name: Optional[str]            # Название услуги (если ID еще нет)
    master_id: Optional[int]               # ID мастера
    master_name: Optional[str]              # Имя мастера
    slot_time: Optional[str]               # Время слота (формат YYYY-MM-DD HH:MM)
    client_name: Optional[str]              # Имя клиента
    client_phone: Optional[str]            # Телефон клиента
    dialog_step: str                       # Текущий шаг диалога (из DialogStep)
