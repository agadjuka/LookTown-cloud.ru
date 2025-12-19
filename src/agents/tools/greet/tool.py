"""
Инструмент для приветствия клиента
"""
from pydantic import BaseModel
from yandex_cloud_ml_sdk._threads.thread import Thread

try:
    from ....services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class Greet(BaseModel):
    """
    Если клиент написал только приветствие.
    """
    
    def process(self, thread: Thread) -> str:
        """
        Приветствие клиента
        
        Returns:
            Приветственное сообщение
        """
        return "Поприветствуй клиента так:\nДобрый день!\nНа связи менеджер LookTown 🌻\nЧем могу вам помочь?"

