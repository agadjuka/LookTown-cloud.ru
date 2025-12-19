"""
Парсер для извлечения описаний инструментов и их полей из файлов.
"""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from registry_loader import setup_packages, load_registry


class ToolsParser:
    """Класс для парсинга описаний инструментов из файлов."""
    
    def __init__(self, project_root: Path):
        """Инициализация парсера.
        
        Args:
            project_root: Корневая директория проекта
        """
        self.project_root = Path(project_root)
        self.tools_dir = self.project_root / "src" / "agents" / "tools"
    
    def parse_all_tools(self) -> Dict[str, Dict[str, Any]]:
        """Извлекает описания всех инструментов.
        
        Returns:
            Словарь {tool_name: {description: str, parameters: {param_name: description}}}
        """
        try:
            setup_packages(self.project_root, [
                ("src", self.project_root / "src"),
                ("src.agents", self.project_root / "src" / "agents"),
                ("src.agents.tools", self.tools_dir),
            ])
            
            registry_file = self.tools_dir / "registry.py"
            registry_module = load_registry(registry_file, "src.agents.tools.registry", "src.agents.tools")
            
            if registry_module is None:
                print(f"[WARNING] Не удалось загрузить реестр инструментов из {registry_file}")
                return {}
            
            registry = registry_module.get_registry()
            tools = registry.get_all_tools()
            
            result = {}
            for tool_class in tools:
                tool_name = tool_class.__name__
                tool_file = self._find_tool_file(tool_name)
                
                if tool_file:
                    tool_info = self._parse_tool_file(tool_file, tool_name)
                    result[tool_name] = tool_info
                else:
                    print(f"[WARNING] Файл для инструмента {tool_name} не найден")
                    result[tool_name] = {
                        "description": tool_class.__doc__ or "",
                        "parameters": {}
                    }
            
            return result
        except Exception as e:
            import traceback
            print(f"[ERROR] Ошибка парсинга инструментов: {e}\n{traceback.format_exc()}")
            return {}
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Находит файл с инструментом.
        
        Args:
            tool_name: Имя класса инструмента
            
        Returns:
            Путь к файлу или None
        """
        # Ищем во всех файлах в tools_dir
        for file_path in self.tools_dir.glob("*.py"):
            if file_path.name == "__init__.py" or file_path.name == "registry.py":
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                # Проверяем, есть ли в файле класс с таким именем
                if re.search(rf'^class {tool_name}\(', content, re.MULTILINE):
                    return file_path
            except Exception as e:
                print(f"[WARNING] Ошибка чтения файла {file_path}: {e}")
        
        return None
    
    def _parse_tool_file(self, file_path: Path, tool_name: str) -> Dict[str, Any]:
        """Парсит файл инструмента и извлекает описания.
        
        Args:
            file_path: Путь к файлу
            tool_name: Имя класса инструмента
            
        Returns:
            Словарь с описанием инструмента и его полей
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            
            # Извлекаем docstring класса (описание инструмента)
            class_pattern = rf'class {tool_name}\(.*?\):\s*("""(.*?)"""|\'\'\'(.*?)\'\'\')'
            match = re.search(class_pattern, content, re.DOTALL)
            
            description = ""
            if match:
                # Берем либо тройные двойные, либо тройные одинарные кавычки
                description = match.group(2) or match.group(3) or ""
                description = description.strip()
            
            # Извлекаем описания полей
            parameters = {}
            
            # Находим область класса
            class_pattern = rf'class {tool_name}\([^)]*\):.*?(?=\nclass |\Z)'
            class_match = re.search(class_pattern, content, re.DOTALL)
            
            if class_match:
                class_content = class_match.group(0)
                
                # Ищем все Field с description внутри класса
                # Сначала находим все объявления полей с Field
                # Паттерн: param_name: type = Field(...)
                field_decl_pattern = rf'(\w+)\s*:\s*[^=]*=\s*Field\s*\('
                
                # Находим все начала Field
                field_starts = list(re.finditer(field_decl_pattern, class_content))
                
                for field_start_match in field_starts:
                    param_name = field_start_match.group(1)
                    start_pos = field_start_match.end()
                    
                    # Находим соответствующую закрывающую скобку Field
                    # Считаем открывающие и закрывающие скобки
                    bracket_count = 1
                    pos = start_pos
                    description_match = None
                    
                    while pos < len(class_content) and bracket_count > 0:
                        if class_content[pos] == '(':
                            bracket_count += 1
                        elif class_content[pos] == ')':
                            bracket_count -= 1
                        
                        # Ищем description внутри Field
                        if bracket_count > 0:
                            desc_pattern = r'description\s*=\s*["\'](.*?)["\']'
                            desc_match = re.search(desc_pattern, class_content[start_pos:pos], re.DOTALL)
                            if desc_match:
                                description_match = desc_match
                        
                        pos += 1
                    
                    if description_match:
                        param_description = description_match.group(1)
                        # Убираем лишние пробелы и переносы строк
                        param_description = re.sub(r'\s+', ' ', param_description).strip()
                        parameters[param_name] = param_description
            
            return {
                "description": description,
                "parameters": parameters
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Ошибка парсинга файла {file_path}: {e}\n{traceback.format_exc()}")
            return {
                "description": "",
                "parameters": {}
            }

