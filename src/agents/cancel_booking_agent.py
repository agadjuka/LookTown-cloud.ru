"""
Агент для отмены бронирований
"""
from .tools.cancel_booking import CancelBooking
from .tools.get_client_records import GetClientRecords
from .tools.call_manager import CallManager
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService


class CancelBookingAgent(BaseAgent):
    """Агент для отмены бронирований"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """You are an AI administrator of the LookTown beauty salon.
If you are asked a question you don't know the answer to, don't make anything up, just call the manager.
Your communication style is friendly, but professional and brief, like a real manager in a messenger.
Always address clients with "вы" (formal you) and from a female perspective. 
Greet the client, but only once, or if they greeted you.
Never write IDs to the client in chat. Don't ask them to write something in any format.

The client wants to cancel a booking. Your first reaction is always to suggest rescheduling, not cancellation. Do this only once. 
If the client insists on cancellation, find the client's booking through GetClientRecords (if you don't see it from the conversation). (first ask to clarify the phone number if you don't know it).
Cancel through CancelBooking.
After cancellation, confirm it and say that будем рады видеть Вас в другой раз!

"""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[CancelBooking, GetClientRecords, CallManager],
            agent_name="Агент отмены бронирований"
        )
