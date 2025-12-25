"""
Обновлятор для сохранения промптов в подграф бронирования (Booking Subgraph)
"""

import re
from pathlib import Path
from typing import Optional


class BookingGraphUpdater:
    """Класс для обновления промптов в подграфе бронирования."""
    
    def __init__(self, project_root: Path):
        """Инициализация обновлятора.
        
        Args:
            project_root: Корневая директория проекта
        """
        self.project_root = Path(project_root)
        self.booking_dir = self.project_root / "src" / "graph" / "booking"
    
    def _read_content(self, file_path: Path) -> str:
        """Читает содержимое файла."""
        return file_path.read_text(encoding="utf-8")
    
    def _write_content(self, file_path: Path, content: str) -> None:
        """Записывает содержимое в файл."""
        file_path.write_text(content, encoding="utf-8")
    
    def update_analyzer_prompt(self, new_prompt: str) -> None:
        """Обновляет промпт в analyzer.py"""
        file_path = self.booking_dir / "analyzer.py"
        content = self._read_content(file_path)
        
        # Ищем и заменяем system_prompt = f"""..."""
        pattern = r'(system_prompt\s*=\s*f?""").*?(""")'
        replacement = rf'\1{new_prompt}\2'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if new_content == content:
            raise ValueError("Не удалось найти промпт для обновления в analyzer.py")
        
        self._write_content(file_path, new_content)
    
    def update_service_manager_prompt(self, new_prompt: str) -> None:
        """Обновляет промпт в service_manager.py"""
        file_path = self.booking_dir / "nodes" / "service_manager.py"
        content = self._read_content(file_path)
        
        # Ищем и заменяем SYSTEM_PROMPT = """..."""
        pattern = r'(SYSTEM_PROMPT\s*=\s*""").*?(""")'
        replacement = rf'\1{new_prompt}\2'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if new_content == content:
            raise ValueError("Не удалось найти промпт для обновления в service_manager.py")
        
        self._write_content(file_path, new_content)
    
    def update_slot_manager_prompt(self, new_prompt: str) -> None:
        """Обновляет шаблон промпта в slot_manager.py"""
        file_path = self.booking_dir / "nodes" / "slot_manager.py"
        content = self._read_content(file_path)
        
        # Ищем и заменяем prompt = f"""...""" внутри функции _build_system_prompt
        pattern = r'(prompt\s*=\s*f?""").*?(""")'
        replacement = rf'\1{new_prompt}\2'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if new_content == content:
            raise ValueError("Не удалось найти промпт для обновления в slot_manager.py")
        
        self._write_content(file_path, new_content)
    
    def update_contact_collector_prompt(self, new_prompt: str) -> None:
        """Обновляет шаблон промпта в contact_collector.py"""
        file_path = self.booking_dir / "nodes" / "contact_collector.py"
        content = self._read_content(file_path)
        
        # Ищем и заменяем system_prompt = f"""..."""
        pattern = r'(system_prompt\s*=\s*f?""").*?(""")'
        replacement = rf'\1{new_prompt}\2'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if new_content == content:
            raise ValueError("Не удалось найти промпт для обновления в contact_collector.py")
        
        self._write_content(file_path, new_content)
    
    def update_finalizer_prompt(self, new_prompt: str) -> None:
        """Обновляет шаблон промпта в finalizer.py"""
        file_path = self.booking_dir / "nodes" / "finalizer.py"
        content = self._read_content(file_path)
        
        # Ищем и заменяем system_prompt = f"""..."""
        pattern = r'(system_prompt\s*=\s*f?""").*?(""")'
        replacement = rf'\1{new_prompt}\2'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if new_content == content:
            raise ValueError("Не удалось найти промпт для обновления в finalizer.py")
        
        self._write_content(file_path, new_content)













