"""
Парсер для извлечения промптов из подграфа бронирования (Booking Subgraph)
"""

import re
from pathlib import Path
from typing import Dict, List, Any


class BookingGraphParser:
    """Класс для парсинга промптов из подграфа бронирования."""
    
    def __init__(self, project_root: Path):
        """Инициализация парсера.
        
        Args:
            project_root: Корневая директория проекта
        """
        self.project_root = Path(project_root)
        self.booking_dir = self.project_root / "src" / "graph" / "booking"
    
    def parse(self) -> Dict[str, Any]:
        """Извлекает все промпты из подграфа бронирования.
        
        Returns:
            Словарь с промптами узлов
        """
        nodes = {
            "analyzer": self._parse_analyzer(),
            "service_manager": self._parse_service_manager(),
            "slot_manager": self._parse_slot_manager(),
            "contact_collector": self._parse_contact_collector(),
            "finalizer": self._parse_finalizer(),
        }
        
        # Логируем результаты
        for node_key, node_data in nodes.items():
            has_prompt = bool(node_data.get("prompt"))
            print(f"[DEBUG BookingGraph] Узел {node_key}: промпт {'найден' if has_prompt else 'НЕ НАЙДЕН'}")
        
        return {
            "nodes": nodes
        }
    
    def _parse_analyzer(self) -> Dict[str, Any]:
        """Извлекает промпт из analyzer.py"""
        file_path = self.booking_dir / "analyzer.py"
        if not file_path.exists():
            return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
        
        content = file_path.read_text(encoding="utf-8")
        
        # Ищем системный промпт в функции booking_analyzer_node
        # Паттерн: system_prompt = f"""...""" (может быть f-string или обычная строка)
        # Ищем между system_prompt = и следующим """
        pattern = r'system_prompt\s*=\s*f?"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            prompt = match.group(1).strip()
            return {
                "prompt": prompt,
                "file": str(file_path.relative_to(self.project_root)),
                "node_type": "analyzer"
            }
        
        return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
    
    def _parse_service_manager(self) -> Dict[str, Any]:
        """Извлекает промпт из service_manager.py"""
        file_path = self.booking_dir / "nodes" / "service_manager.py"
        if not file_path.exists():
            return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
        
        content = file_path.read_text(encoding="utf-8")
        
        # Ищем SYSTEM_PROMPT = """..."""
        pattern = r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            return {
                "prompt": match.group(1).strip(),
                "file": str(file_path.relative_to(self.project_root)),
                "node_type": "service_manager"
            }
        
        return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
    
    def _parse_slot_manager(self) -> Dict[str, Any]:
        """Извлекает шаблон промпта из slot_manager.py"""
        file_path = self.booking_dir / "nodes" / "slot_manager.py"
        if not file_path.exists():
            return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
        
        content = file_path.read_text(encoding="utf-8")
        
        # Ищем шаблон промпта в функции _build_system_prompt
        # Ищем часть prompt = f"""...""" внутри функции
        pattern = r'prompt\s*=\s*f?"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            prompt = match.group(1).strip()
            # Убираем динамические части (f-strings с переменными)
            prompt = self._clean_dynamic_parts(prompt)
            return {
                "prompt": prompt,
                "file": str(file_path.relative_to(self.project_root)),
                "node_type": "slot_manager",
                "is_template": True
            }
        
        return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
    
    def _parse_contact_collector(self) -> Dict[str, Any]:
        """Извлекает шаблон промпта из contact_collector.py"""
        file_path = self.booking_dir / "nodes" / "contact_collector.py"
        if not file_path.exists():
            return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
        
        content = file_path.read_text(encoding="utf-8")
        
        # Ищем системный промпт
        pattern = r'system_prompt\s*=\s*f?"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            prompt = match.group(1).strip()
            # Убираем динамические части
            prompt = self._clean_dynamic_parts(prompt)
            return {
                "prompt": prompt,
                "file": str(file_path.relative_to(self.project_root)),
                "node_type": "contact_collector",
                "is_template": True
            }
        
        return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
    
    def _parse_finalizer(self) -> Dict[str, Any]:
        """Извлекает шаблон промпта из finalizer.py"""
        file_path = self.booking_dir / "nodes" / "finalizer.py"
        if not file_path.exists():
            return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
        
        content = file_path.read_text(encoding="utf-8")
        
        # Ищем системный промпт
        pattern = r'system_prompt\s*=\s*f?"""(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            prompt = match.group(1).strip()
            # Убираем динамические части
            prompt = self._clean_dynamic_parts(prompt)
            return {
                "prompt": prompt,
                "file": str(file_path.relative_to(self.project_root)),
                "node_type": "finalizer",
                "is_template": True
            }
        
        return {"prompt": "", "file": str(file_path.relative_to(self.project_root))}
    
    def _clean_dynamic_parts(self, prompt: str) -> str:
        """Убирает динамические части из промпта (f-strings с переменными).
        
        Заменяет {variable} на {VARIABLE} для сохранения структуры, но без реальных значений.
        """
        # Заменяем {variable} на {VARIABLE} для сохранения структуры
        # Но оставляем как есть, так как пользователь может редактировать шаблон
        return prompt

