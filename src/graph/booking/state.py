"""
Состояние для подграфа бронирования (Booking Subgraph)
"""
from typing import TypedDict, Optional


class BookingSubState(TypedDict, total=False):
    """Состояние подграфа бронирования"""
    service_id: Optional[int]              # ID услуги
    service_name: Optional[str]            # Название услуги (если ID еще нет)
    master_id: Optional[int]               # ID мастера
    master_name: Optional[str]              # Имя мастера
    slot_time: Optional[str]               # Время слота (формат YYYY-MM-DD HH:MM)
    client_name: Optional[str]              # Имя клиента
    client_phone: Optional[str]            # Телефон клиента
    is_finalized: Optional[bool]           # Флаг завершения бронирования
