"""
Определение стадий диалога
Соответствует стадиям из dialogue_patterns.json
"""
from enum import Enum


class DialogueStage(str, Enum):
    """Стадии диалога"""
    BOOKING = "booking"                        # Бронирование услуги
    CANCELLATION_REQUEST = "cancellation_request"  # Запрос на отмену записи
    RESCHEDULE = "reschedule"                 # Перенос записи
    VIEW_MY_BOOKING = "view_my_booking"        # Просмотр своих записей