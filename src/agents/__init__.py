"""
Пакет агентов для LangGraph
"""
from .base_agent import BaseAgent
from .dialogue_stages import DialogueStage
from .stage_detector_agent import StageDetectorAgent, StageDetection
from .booking_agent import BookingAgent
from .cancel_booking_agent import CancelBookingAgent
from .reschedule_agent import RescheduleAgent

__all__ = [
    "BaseAgent",
    "DialogueStage",
    "StageDetectorAgent",
    "StageDetection",
    "BookingAgent",
    "CancelBookingAgent",
    "RescheduleAgent",
]

