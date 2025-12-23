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
    slot_time_verified: Optional[bool]     # Флаг проверки доступности времени
    client_name: Optional[str]              # Имя клиента
    client_phone: Optional[str]            # Телефон клиента
    is_finalized: Optional[bool]           # Флаг завершения бронирования
    service_details_needed: Optional[bool] # Флаг необходимости ответа на вопрос об услуге
