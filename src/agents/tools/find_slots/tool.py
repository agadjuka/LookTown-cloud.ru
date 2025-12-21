"""
Инструмент для поиска доступных временных слотов
"""
import asyncio
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from ..common.yclients_service import YclientsService
from .logic import find_slots_by_period

try:
    from ....services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class FindSlots(BaseModel):
    """
    Найти доступные временные слоты для услуги.
    """
    
    service_id: int = Field(
        description="ID услуги. Получи из GetServices"
    )
    
    time_period: Optional[str] = Field(
        default=None,
        description="Период времени (необязательное поле). Поддерживаемые форматы: 'morning' (9:00-11:00), 'day' (11:00-17:00), 'evening' (17:00-22:00); конкретное время '16:00' интервал '16:00-19:00' 'before 11:00'; 'after 16:00' (после 16:00)."
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (необязательное поле). Заполняй только если клиент хочет записаться к конкретному мастеру."
    )
    
    master_id: Optional[int] = Field(
        default=None,
        description="ID мастера (необязательное поле). Заполняй только если знаешь точный ID мастера. Если указан master_id, то master_name игнорируется."
    )
    
    date: Optional[str] = Field(
        default=None,
        description="Конкретная дата (необязательное поле). Формат: 'YYYY-MM-DD' Если клиент просит найти ближайшую дату или справшивает когда есть свободые слоты - оставь пустым."
    )
    
    date_range: Optional[str] = Field(
        default=None,
        description="Интервал дат (необязательное поле). Формат: 'YYYY-MM-DD:YYYY-MM-DD'"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск доступных временных слотов с фильтрацией по периоду времени
        
        Returns:
            Отформатированный список доступных временных интервалов по датам
        """
        try:
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            result = asyncio.run(
                find_slots_by_period(
                    yclients_service=yclients_service,
                    service_id=self.service_id,
                    time_period=self.time_period or "",
                    master_name=self.master_name,
                    master_id=self.master_id,
                    date=self.date,
                    date_range=self.date_range
                )
            )
            
            if result.get('error'):
                return f"Ошибка: {result['error']}"
            
            service_title = result.get('service_title', 'Услуга')
            time_period = result.get('time_period', '')
            masters = result.get('masters', [])
            
            if not masters:
                if time_period:
                    period_display = self._format_time_period_display(time_period)
                    period_text = f" {period_display}"
                else:
                    period_text = ""
                
                if self.master_name or self.master_id:
                    master_display = self.master_name or f"мастера {self.master_id}"
                    if self.date:
                        return f"К сожалению, у {master_display} нет свободных слотов{period_text} для услуги '{service_title}' на {self.date}."
                    elif self.date_range:
                        return f"К сожалению, у {master_display} нет свободных слотов{period_text} для услуги '{service_title}' в указанный период."
                    else:
                        return f"К сожалению, у {master_display} нет свободных слотов{period_text} для услуги '{service_title}' в ближайшие дни."
                else:
                    if self.date:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' на {self.date}."
                    elif self.date_range:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' в указанный период."
                    else:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' в ближайшие дни."
            
            if time_period:
                period_display = self._format_time_period_display(time_period)
                period_text = f" {period_display}"
            else:
                period_text = ""
            
            result_lines = []
            result_lines.append(f"Доступные слоты{period_text} для услуги '{service_title}':\n")
            
            # Выводим слоты для каждого мастера отдельно
            for master_data in masters:
                master_name = master_data.get('master_name', 'Неизвестный мастер')
                master_results = master_data.get('results', [])
                
                if not master_results:
                    continue
                
                result_lines.append(f"Мастер {master_name}:")
                
                for day_result in master_results:
                    date = day_result['date']
                    slots = day_result['slots']
                    
                    try:
                        date_obj = datetime.strptime(date, "%Y-%m-%d")
                        formatted_date = date_obj.strftime("%d.%m.%Y")
                    except:
                        formatted_date = date
                    
                    slots_text = " | ".join(slots)
                    result_lines.append(f"  {formatted_date}: {slots_text}")
                
                result_lines.append("")  # Пустая строка между мастерами
            
            return "\n".join(result_lines).strip()
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindSlots: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске слотов: {e}", exc_info=True)
            return f"Ошибка при поиске доступных слотов: {str(e)}"
    
    def _format_time_period_display(self, time_period: str) -> str:
        """Форматирует период времени для отображения пользователю"""
        time_period_lower = time_period.strip().lower()
        
        period_names = {
            'morning': 'утром',
            'day': 'днем',
            'evening': 'вечером'
        }
        
        if time_period_lower in period_names:
            return period_names[time_period_lower]
        
        if time_period_lower.startswith("before "):
            time_str = time_period[7:].strip()
            return f"до {time_str}"
        
        if time_period_lower.startswith("after "):
            time_str = time_period[6:].strip()
            return f"после {time_str}"
        
        if '-' in time_period:
            return f"в период {time_period}"
        
        return f"около {time_period}"

