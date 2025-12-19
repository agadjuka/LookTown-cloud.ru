"""
Обновлятор для сохранения описаний инструментов и их полей в файлы.
"""

import re
from pathlib import Path
from typing import Dict, Optional
from registry_loader import setup_packages, load_registry


class ToolsUpdater:
    """Класс для обновления описаний инструментов в файлах."""
    
    def __init__(self, project_root: Path):
        """Инициализация обновлятора.
        
        Args:
            project_root: Корневая директория проекта
        """
        self.project_root = Path(project_root)
        self.tools_dir = self.project_root / "src" / "agents" / "tools"
    
    def update_tool_description(self, tool_name: str, new_description: str) -> None:
        """Обновляет описание инструмента (docstring класса).
        
        Args:
            tool_name: Имя класса инструмента
            new_description: Новое описание
        """
        tool_file = self._find_tool_file(tool_name)
        if not tool_file:
            raise FileNotFoundError(f"Файл для инструмента {tool_name} не найден")
        
        content = tool_file.read_text(encoding="utf-8")
        new_content = self._update_class_docstring(content, tool_name, new_description)
        tool_file.write_text(new_content, encoding="utf-8")
    
    def update_parameter_description(self, tool_name: str, param_name: str, new_description: str) -> None:
        """Обновляет описание поля инструмента.
        
        Args:
            tool_name: Имя класса инструмента
            param_name: Имя поля
            new_description: Новое описание
        """
        tool_file = self._find_tool_file(tool_name)
        if not tool_file:
            raise FileNotFoundError(f"Файл для инструмента {tool_name} не найден")
        
        content = tool_file.read_text(encoding="utf-8")
        new_content = self._update_field_description(content, tool_name, param_name, new_description)
        tool_file.write_text(new_content, encoding="utf-8")
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Находит файл с инструментом.
        
        Args:
            tool_name: Имя класса инструмента
            
        Returns:
            Путь к файлу или None
        """
        for file_path in self.tools_dir.glob("*.py"):
            if file_path.name == "__init__.py" or file_path.name == "registry.py":
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                if re.search(rf'^class {tool_name}\(', content, re.MULTILINE):
                    return file_path
            except Exception:
                pass
        
        return None
    
    def _update_class_docstring(self, content: str, tool_name: str, new_description: str) -> str:
        """Обновляет docstring класса.
        
        Args:
            content: Исходное содержимое файла
            tool_name: Имя класса
            new_description: Новое описание
            
        Returns:
            Обновленное содержимое файла
        """
        # Паттерн для поиска класса с docstring
        # Ищем: class ToolName(...): """..."""
        pattern = rf'(class {tool_name}\([^)]*\):\s*)(["\']{{3}})(.*?)(["\']{{3}})'
        
        def replace_docstring(match):
            class_declaration = match.group(1)
            quote_start = match.group(2)
            quote_end = match.group(4)
            return f'{class_declaration}{quote_start}{new_description}{quote_end}'
        
        new_content = re.sub(pattern, replace_docstring, content, flags=re.DOTALL)
        
        # Если не нашли docstring, добавляем его после объявления класса
        if new_content == content:
            pattern = rf'(class {tool_name}\([^)]*\):\s*)'
            replacement = rf'\1"""\n{new_description}\n"""'
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        
        return new_content
    
    def _update_field_description(self, content: str, tool_name: str, param_name: str, new_description: str) -> str:
        """Обновляет описание поля в Field.
        
        Args:
            content: Исходное содержимое файла
            tool_name: Имя класса
            param_name: Имя поля
            new_description: Новое описание
            
        Returns:
            Обновленное содержимое файла
        """
        # Находим область класса
        class_pattern = rf'class {tool_name}\([^)]*\):.*?(?=\nclass |\Z)'
        class_match = re.search(class_pattern, content, re.DOTALL)
        
        if not class_match:
            raise ValueError(f"Класс {tool_name} не найден в файле")
        
        class_content = class_match.group(0)
        class_start = class_match.start()
        class_end = class_match.end()
        
        # Ищем поле внутри класса
        # Находим начало Field для param_name
        field_decl_pattern = rf'({param_name}\s*:\s*[^=]*=\s*Field\s*\()'
        field_start_match = re.search(field_decl_pattern, class_content)
        
        if not field_start_match:
            raise ValueError(f"Поле {param_name} не найдено в классе {tool_name}")
        
        start_pos = field_start_match.end()
        bracket_count = 1
        pos = start_pos
        field_end_pos = None
        
        # Находим закрывающую скобку Field
        while pos < len(class_content) and bracket_count > 0:
            if class_content[pos] == '(':
                bracket_count += 1
            elif class_content[pos] == ')':
                bracket_count -= 1
                if bracket_count == 0:
                    field_end_pos = pos
                    break
            pos += 1
        
        if field_end_pos is None:
            raise ValueError(f"Не удалось найти закрывающую скобку для поля {param_name}")
        
        # Извлекаем содержимое Field
        field_content = class_content[start_pos:field_end_pos]
        
        # Ищем description в содержимом Field более точно
        # Ищем начало description=
        desc_start_pattern = r'description\s*=\s*(["\'])'
        desc_start_match = re.search(desc_start_pattern, field_content)
        
        if desc_start_match:
            # Нашли начало description, теперь нужно найти правильную закрывающую кавычку
            quote_char = desc_start_match.group(1)
            desc_start_pos = desc_start_match.start()
            desc_value_start = desc_start_match.end()
            
            # Ищем закрывающую кавычку, учитывая что она может быть экранирована
            # Проходим по строке и ищем неэкранированную закрывающую кавычку
            desc_value_end = None
            pos = desc_value_start
            while pos < len(field_content):
                if field_content[pos] == '\\':
                    # Пропускаем экранированный символ
                    pos += 2
                    continue
                elif field_content[pos] == quote_char:
                    # Нашли закрывающую кавычку
                    desc_value_end = pos
                    break
                pos += 1
            
            if desc_value_end is not None:
                # Заменяем существующее описание
                # Сохраняем часть до description и после закрывающей кавычки
                before_desc = field_content[:desc_start_pos]
                after_desc = field_content[desc_value_end + 1:]
                
                # Убираем лишние запятые и пробелы
                before_desc = before_desc.rstrip().rstrip(',')
                after_desc = after_desc.lstrip()
                if after_desc and not after_desc.startswith(','):
                    after_desc = ', ' + after_desc if after_desc else ''
                
                # Формируем новое содержимое
                if before_desc.strip():
                    new_field_content = f'{before_desc}, description="{new_description}"{after_desc}'
                else:
                    new_field_content = f'description="{new_description}"{after_desc}'
            else:
                # Не нашли закрывающую кавычку, просто заменяем все после description=
                before_desc = field_content[:desc_start_pos].rstrip().rstrip(',')
                new_field_content = f'{before_desc}, description="{new_description}"'
        else:
            # Добавляем description
            field_content_clean = field_content.strip()
            if field_content_clean:
                # Убираем лишние запятые в конце
                field_content_clean = field_content_clean.rstrip().rstrip(',')
                new_field_content = f'{field_content_clean}, description="{new_description}"'
            else:
                new_field_content = f'description="{new_description}"'
        
        # Заменяем содержимое Field в классе
        new_class_content = (
            class_content[:start_pos] +
            new_field_content +
            class_content[field_end_pos:]
        )
        
        # Заменяем содержимое класса в исходном файле
        new_content = content[:class_start] + new_class_content + content[class_end:]
        
        return new_content

