"""
Инструменты для работы с каталогом услуг и бронированием
"""
from .get_categories import GetCategories
from .find_slots import FindSlots
from .create_booking import CreateBooking
from .view_service import ViewService
from .find_service import FindService
from .get_client_records import GetClientRecords
from .cancel_booking import CancelBooking
from .reschedule_booking import RescheduleBooking
from .call_manager import CallManager
from .about_salon import AboutSalon
from .masters import Masters

__all__ = [
    # Инструменты каталога услуг
    "GetCategories",
    "ViewService",
    # Инструменты бронирования
    "FindSlots",
    "CreateBooking",
    "FindService",
    # Инструменты для работы с записями клиентов
    "GetClientRecords",
    "CancelBooking",
    "RescheduleBooking",
    # Инструмент передачи менеджеру
    "CallManager",
    # Инструмент информации о салоне
    "AboutSalon",
    # Инструмент информации о мастерах
    "Masters",
]
