"""
Инструмент для получения детальной информации об услуге
"""
import asyncio
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import view_service_logic

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class ViewService(BaseModel):
    """
    Get detailed information about a service by its ID.
    Use when you need to find out details about a service: name, price, duration, list of masters.
    """
    
    service_id: int = Field(
        description="Service ID. Get from FindService"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Получение детальной информации об услуге
        
        Returns:
            Отформатированная информация об услуге
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            result = asyncio.run(
                view_service_logic(
                    yclients_service=yclients_service,
                    service_id=self.service_id
                )
            )
            
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                message = result.get('message', '')
                status = result.get('status')
                
                if error == 'bad_service_id':
                    return f"Ошибка: {message}"
                elif error == 'yclients_http_error':
                    return f"Ошибка при обращении к API Yclients (HTTP {status}): {message}"
                else:
                    if message:
                        return f"Ошибка: {error}. {message}"
                    return f"Ошибка: {error}"
            
            service = result.get('service', {})
            
            result_lines = []
            
            title = service.get('title', 'Неизвестно')
            service_id = service.get('id', 'Не указан')
            result_lines.append(f"Услуга: {title} (ID: {service_id})")
            
            duration_sec = service.get('duration_sec')
            if duration_sec:
                duration_min = duration_sec // 60
                result_lines.append(f"Продолжительность: {duration_min} минут")
            
            price_min = service.get('price_min')
            price_max = service.get('price_max')
            if price_min is not None or price_max is not None:
                if price_min == price_max:
                    price_value = int(price_min) if price_min is not None else price_min
                    result_lines.append(f"Цена: {price_value} руб.")
                else:
                    price_min_value = int(price_min) if price_min is not None else 'от'
                    price_max_value = int(price_max) if price_max is not None else 'до'
                    result_lines.append(f"Цена: {price_min_value} - {price_max_value} руб.")
            
            comment = service.get('comment')
            if comment:
                result_lines.append(f"\nОписание:\n{comment}")
            
            staff = service.get('staff', [])
            if staff:
                result_lines.append(f"\nМастера:")
                for master in staff:
                    master_name = master.get('name', 'Неизвестно')
                    master_id = master.get('id', 'Не указан')
                    result_lines.append(f"  • {master_name} (ID: {master_id})")
            else:
                result_lines.append("\nМастера не найдены")
            
            result_lines.append("\n((Отправь клиенту этот текст, сохраняй форматирование, не пиши ничего от себя, если ты не нашёл ответ на вопрос клиента, позови менеджера))")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации ViewService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при получении информации об услуге: {e}", exc_info=True)
            return f"Ошибка при получении информации об услуге: {str(e)}"

