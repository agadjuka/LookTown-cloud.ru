"""
Простая система логирования запросов к LLM
Сохраняет форматированный JSON для удобного просмотра
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock


class LLMRequestLogger:
    """Простой логгер - сохраняет форматированный JSON запросов к LLM"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Проверяем, нужно ли сохранять логи
        # Поддерживаются две переменные окружения:
        # - ENABLE_LLM_LOGGING (приоритетная): 'true' - включить, 'false' - отключить
        # - DISABLE_DEBUG_LOGS (для обратной совместимости): 'true' - отключить
        # По умолчанию логирование включено
        enable_logging = os.getenv('ENABLE_LLM_LOGGING', '').lower()
        disable_logging = os.getenv('DISABLE_DEBUG_LOGS', '').lower()
        
        if enable_logging:
            # Новая переменная имеет приоритет
            self.logging_enabled = enable_logging == 'true'
        elif disable_logging:
            # Старая переменная для обратной совместимости
            self.logging_enabled = disable_logging != 'true'
        else:
            # По умолчанию включено
            self.logging_enabled = True
        
        if self.logging_enabled:
            self.logs_dir = Path("logs")
            self.logs_dir.mkdir(exist_ok=True)
        else:
            self.logs_dir = None
        
        self._file_lock = Lock()
        self._request_counter = 0
        self._last_request_id = 0
        
        self._initialized = True
    
    def _to_dict_recursive(self, obj: Any) -> Any:
        """Рекурсивно преобразует объекты в словари"""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [self._to_dict_recursive(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self._to_dict_recursive(v) for k, v in obj.items()}
        
        # Если есть метод model_dump (Pydantic v2)
        if hasattr(obj, 'model_dump'):
            return self._to_dict_recursive(obj.model_dump())
        # Если есть метод dict (Pydantic v1)
        if hasattr(obj, 'dict'):
            return self._to_dict_recursive(obj.dict())
        # Если есть __dict__
        if hasattr(obj, '__dict__'):
            return {
                k: self._to_dict_recursive(v) 
                for k, v in obj.__dict__.items() 
                if not k.startswith('_')
            }
        
        # Fallback
        return str(obj)
    
    def save_request(self, request_data: Dict[str, Any], agent_name: Optional[str] = None):
        """
        Сохранить запрос к LLM как чистый JSON файл
        
        Args:
            request_data: Словарь с данными запроса (то, что реально отправляется в API)
            agent_name: Имя агента (опционально)
        """
        if not self.logging_enabled or not self.logs_dir:
            return
        
        try:
            with self._file_lock:
                self._request_counter += 1
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                
                # Имя файла с номером запроса и временной меткой
                filename = self.logs_dir / f"request_{self._request_counter}_{timestamp}.json"
                
                # Преобразуем все в словарь
                clean_data = self._to_dict_recursive(request_data)
                
                # Сохраняем ID запроса
                request_id = self._request_counter
                self._last_request_id = request_id
                
                # Добавляем метаданные
                final_data = {
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "agent_name": agent_name or "Unknown",
                    "request": clean_data
                }
                
                # Сохраняем как форматированный JSON для читаемости
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(final_data, f, ensure_ascii=False, indent=2)
                
                return request_id
                
        except Exception as e:
            print(f"Ошибка сохранения запроса: {e}")
            return None
    
    def save_response(self, response_data: Any, agent_name: Optional[str] = None, request_id: Optional[int] = None):
        """
        Сохранить ответ от LLM как чистый JSON файл
        
        Args:
            response_data: Объект ответа от API
            agent_name: Имя агента (опционально)
            request_id: ID запроса для связи с запросом (опционально)
        """
        if not self.logging_enabled or not self.logs_dir:
            return
        
        try:
            with self._file_lock:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                
                # Имя файла
                if request_id:
                    filename = self.logs_dir / f"response_{request_id}_{timestamp}.json"
                else:
                    filename = self.logs_dir / f"response_{timestamp}.json"
                
                # Преобразуем ответ в словарь
                clean_data = self._to_dict_recursive(response_data)
                
                # Добавляем метаданные
                final_data = {
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "agent_name": agent_name or "Unknown",
                    "response": clean_data
                }
                
                # Сохраняем как форматированный JSON для читаемости
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(final_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Ошибка сохранения ответа: {e}")


# Глобальный экземпляр логгера
llm_request_logger = LLMRequestLogger()
