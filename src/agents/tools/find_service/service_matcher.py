"""
Модуль для умного поиска услуг с использованием морфологического анализа
"""
from typing import List, Tuple, Dict, Set
from rapidfuzz import fuzz
import re

try:
    import pymorphy3
    MORPH_AVAILABLE = True
except ImportError:
    MORPH_AVAILABLE = False


class ServiceMatcher:
    """Класс для умного сопоставления услуг с поисковыми запросами"""
    
    # Важные предлоги, которые НЕ должны фильтроваться (whitelist)
    IMPORTANT_PREPOSITIONS: Set[str] = {'с', 'без', 'от', 'до', 'для', 'на'}
    
    # Пары конфликтов/антонимов: (множество терминов запроса, множество терминов услуги)
    # Если в запросе есть термины из первого множества, а в услуге - из второго, применяется штраф
    CONFLICT_PAIRS: List[Tuple[Set[str], Set[str]]] = [
        # "с покрытием" vs "без покрытия"
        ({'с', 'покрытие', 'покрытием', 'покрытия'}, {'без'}),
        ({'без', 'без покрытия'}, {'с', 'покрытие', 'покрытием', 'покрытия'}),
        # "маникюр" vs "педикюр" (строгий конфликт, если не комбо)
        ({'маникюр', 'маникюра', 'маникюром'}, {'педикюр', 'педикюра', 'педикюром'}),
        ({'педикюр', 'педикюра', 'педикюром'}, {'маникюр', 'маникюра', 'маникюром'}),
        # Дополнительные конфликты для салона красоты
        ({'окрашивание', 'окраска', 'окрасить'}, {'осветление', 'осветлить', 'блонд'}),
        ({'осветление', 'осветлить', 'блонд'}, {'окрашивание', 'окраска', 'окрасить'}),
        ({'короткая', 'короткие', 'короткое'}, {'длинная', 'длинные', 'длинное'}),
        ({'длинная', 'длинные', 'длинное'}, {'короткая', 'короткие', 'короткое'}),
    ]
    
    def __init__(self):
        """Инициализация морфологического анализатора"""
        self.morph = None
        if MORPH_AVAILABLE:
            try:
                self.morph = pymorphy3.MorphAnalyzer()
            except Exception:
                pass
    
    def _normalize_text(self, text: str) -> str:
        """
        Нормализует текст: приводит к нижнему регистру, убирает лишние пробелы
        
        Args:
            text: Текст для нормализации
            
        Returns:
            Нормализованный текст
        """
        if not text:
            return ""
        # Заменяем специальные символы на пробелы
        text = re.sub(r'[+\-.,;:!?()\[\]{}]', ' ', text)
        # Нормализуем пробелы
        return " ".join(text.lower().strip().split())
    
    def _lemmatize_word(self, word: str) -> str:
        """
        Приводит слово к нормальной форме (лемматизация)
        
        Args:
            word: Слово для лемматизации
            
        Returns:
            Лемма слова
        """
        if not word or len(word) < 2:
            return word
        
        if self.morph:
            try:
                parsed = self.morph.parse(word)[0]
                return parsed.normal_form
            except Exception:
                return word
        
        return word
    
    def _lemmatize_text(self, text: str) -> str:
        """
        Приводит весь текст к нормальным формам слов
        
        Args:
            text: Текст для лемматизации
            
        Returns:
            Текст с лемматизированными словами
        """
        normalized = self._normalize_text(text)
        words = normalized.split()
        lemmatized_words = [self._lemmatize_word(word) for word in words]
        return " ".join(lemmatized_words)
    
    def _get_keywords(self, text: str) -> List[str]:
        """
        Извлекает ключевые слова из текста (исключая служебные слова)
        ВАЖНО: Сохраняет важные предлоги из whitelist, даже если они короткие
        
        Args:
            text: Текст для обработки
            
        Returns:
            Список ключевых слов
        """
        # Служебные слова, которые не важны для поиска
        # НО: важные предлоги (IMPORTANT_PREPOSITIONS) НЕ включаем в стоп-слова
        stop_words = {
            "по", "в", "к", "из", "у", "о", "об",
            "и", "или", "а", "но", "же", "ли", "бы", "то", "как", "что",
            "услуги", "услуга", "услуг", "услугу", "услуге", "услугой",
            "хочу", "нужен", "нужна", "нужно", "нужны",
            "записаться", "запись", "записи"
        }
        
        normalized = self._normalize_text(text)
        words = normalized.split()
        
        # Фильтруем слова: сохраняем важные предлоги и слова длиннее 2 символов
        keywords = [
            w for w in words 
            if (w in self.IMPORTANT_PREPOSITIONS or (w not in stop_words and len(w) > 2))
        ]
        return keywords
    
    def _check_conflicts(self, query_text: str, service_text: str) -> float:
        """
        Проверяет наличие конфликтов/антонимов между запросом и услугой
        
        Args:
            query_text: Текст запроса
            service_text: Текст услуги
            
        Returns:
            Штраф (отрицательное число) или 0, если конфликтов нет
        """
        # Нормализуем и лемматизируем тексты для проверки
        normalized_query = self._normalize_text(query_text)
        normalized_service = self._normalize_text(service_text)
        lemmatized_query = self._lemmatize_text(query_text)
        lemmatized_service = self._lemmatize_text(service_text)
        
        # Создаем множества всех слов (нормализованных и лемматизированных)
        query_words = set(normalized_query.split()) | set(lemmatized_query.split())
        service_words = set(normalized_service.split()) | set(lemmatized_service.split())
        
        # Проверяем каждую пару конфликтов
        for query_terms, service_terms in self.CONFLICT_PAIRS:
            # Проверяем, есть ли в запросе термины из первого множества
            query_has_terms = bool(query_terms & query_words)
            
            # Проверяем, есть ли в услуге термины из второго множества
            service_has_terms = bool(service_terms & service_words)
            
            # Если конфликт обнаружен - применяем штраф
            if query_has_terms and service_has_terms:
                # Значительный штраф: уменьшаем релевантность на 50% или вычитаем 50 баллов
                return -50.0
        
        return 0.0
    
    def calculate_relevance(self, service_title: str, search_query: str) -> float:
        """
        Вычисляет релевантность услуги к поисковому запросу
        
        Args:
            service_title: Название услуги
            search_query: Поисковый запрос
            
        Returns:
            Оценка релевантности (0-100)
        """
        if not service_title or not search_query:
            return 0.0
        
        # Нормализуем тексты
        normalized_title = self._normalize_text(service_title)
        normalized_query = self._normalize_text(search_query)
        
        # Точное совпадение (после нормализации)
        if normalized_title == normalized_query:
            return 100.0
        
        # Лемматизируем тексты для лучшего сопоставления
        lemmatized_title = self._lemmatize_text(service_title)
        lemmatized_query = self._lemmatize_text(search_query)
        
        # Точное совпадение после лемматизации
        if lemmatized_title == lemmatized_query:
            return 95.0
        
        # Извлекаем ключевые слова (теперь с сохранением важных предлогов)
        query_keywords = self._get_keywords(search_query)
        title_keywords = self._get_keywords(service_title)
        
        # Если нет ключевых слов в запросе - низкая релевантность
        if not query_keywords:
            return 0.0
        
        # Лемматизируем ключевые слова
        lemmatized_query_keywords = [self._lemmatize_word(w) for w in query_keywords]
        lemmatized_title_keywords = [self._lemmatize_word(w) for w in title_keywords]
        
        # Подсчитываем совпадения ключевых слов
        query_keywords_set = set(lemmatized_query_keywords)
        title_keywords_set = set(lemmatized_title_keywords)
        matched_keywords = query_keywords_set & title_keywords_set
        missing_keywords = query_keywords_set - title_keywords_set
        
        keyword_match_ratio = len(matched_keywords) / len(query_keywords_set) if query_keywords_set else 0
        
        # КРИТИЧНО: Если отсутствует хотя бы одно ключевое слово - значительный штраф
        if missing_keywords:
            # Штраф пропорционален количеству отсутствующих слов
            penalty = (len(missing_keywords) / len(query_keywords_set)) * 60.0
            # Если отсутствует больше половины ключевых слов - очень низкая релевантность
            if len(missing_keywords) > len(query_keywords_set) / 2:
                # Максимальная релевантность для таких случаев - 30%
                return max(0.0, keyword_match_ratio * 30.0 - penalty)
        
        # Нечеткое сравнение полных текстов
        ratio_full = fuzz.ratio(normalized_title, normalized_query)
        ratio_partial = fuzz.partial_ratio(normalized_title, normalized_query)
        ratio_token = fuzz.token_sort_ratio(normalized_title, normalized_query)
        
        # Нечеткое сравнение лемматизированных текстов
        ratio_lemma = fuzz.ratio(lemmatized_title, lemmatized_query)
        ratio_token_lemma = fuzz.token_sort_ratio(lemmatized_title, lemmatized_query)
        
        # Проверяем, все ли ключевые слова найдены
        all_keywords_found = len(matched_keywords) == len(query_keywords_set) and len(query_keywords_set) > 0
        
        # Проверяем, содержится ли запрос в названии (или наоборот)
        query_in_title = normalized_query in normalized_title or lemmatized_query in lemmatized_title
        title_in_query = normalized_title in normalized_query or lemmatized_title in normalized_query
        
        # Вычисляем итоговую релевантность
        # Базовый вес нечеткого сравнения
        base_relevance = max(ratio_full, ratio_partial, ratio_token, ratio_lemma, ratio_token_lemma)
        
        # Если все ключевые слова найдены - это очень хорошо
        if all_keywords_found:
            # Базовая релевантность на основе совпадения всех ключевых слов
            base_relevance = max(base_relevance, keyword_match_ratio * 100)
            # Бонус за полное совпадение всех ключевых слов
            base_relevance += 25.0
            
            # Дополнительный бонус, если запрос содержится в названии
            if query_in_title:
                base_relevance += 15.0
        else:
            # Если не все ключевые слова найдены - штраф
            penalty = (len(missing_keywords) / len(query_keywords_set)) * 50.0
            base_relevance = max(0.0, base_relevance - penalty)
        
        # Приоритет: если запрос содержится в названии и все ключевые слова найдены
        if query_in_title and all_keywords_found:
            # Запрос содержится в названии и все ключевые слова найдены - высокий приоритет
            base_relevance = max(base_relevance, 85.0)
        elif query_in_title:
            # Запрос содержится в названии - это важный признак релевантности
            # Даже если не все ключевые слова найдены, это все равно релевантно
            if all_keywords_found:
                base_relevance = max(base_relevance, 80.0)
            else:
                # Запрос в названии, но не все слова - средний приоритет, но не отбрасываем
                base_relevance = max(base_relevance, 50.0)
        
        if title_in_query:
            # Название содержится в запросе
            base_relevance = max(base_relevance, 40.0)
        
        # ПРИМЕНЯЕМ ШТРАФ ЗА КОНФЛИКТЫ/АНТОНИМЫ (после базового скоринга, но до финальной проверки)
        conflict_penalty = self._check_conflicts(search_query, service_title)
        base_relevance = max(0.0, base_relevance + conflict_penalty)
        
        # Для коротких запросов (одно слово) делаем более мягкую проверку
        is_single_word_query = len(query_keywords_set) == 1
        
        # Если запрос содержится в названии и все ключевые слова найдены - это точно релевантно
        if query_in_title and all_keywords_found:
            return min(base_relevance, 100.0)
        
        # Фильтрация: если релевантность низкая и не все ключевые слова найдены - отбрасываем
        if base_relevance < 50.0:
            if not matched_keywords:
                return 0.0
            # Для однословных запросов делаем более мягкую проверку
            if is_single_word_query:
                # Если ключевое слово найдено, но релевантность низкая - все равно возвращаем
                if matched_keywords:
                    return max(base_relevance, 30.0)  # Минимум 30% если слово найдено
            else:
                # Для многословных запросов - более строгая проверка
                if keyword_match_ratio < 0.5:
                    return 0.0
        
        return min(base_relevance, 100.0)
    
    def find_best_matches(
        self, 
        services: List[Dict], 
        search_query: str, 
        min_relevance: float = 50.0,
        max_results: int = 15
    ) -> List[Tuple[Dict, float]]:
        """
        Находит наиболее релевантные услуги для поискового запроса
        Использует адаптивный порог для фильтрации результатов
        
        Args:
            services: Список услуг (словари с ключом 'title' или 'name')
            search_query: Поисковый запрос
            min_relevance: Минимальная релевантность для включения в результат (базовый порог)
            max_results: Максимальное количество результатов
            
        Returns:
            Список кортежей (услуга, релевантность), отсортированный по убыванию релевантности
        """
        results = []
        
        # Первый проход: вычисляем релевантность для всех услуг
        for service in services:
            # Получаем название услуги
            service_title = service.get('title', '') or service.get('name', '')
            if not service_title:
                continue
            
            # Вычисляем релевантность
            relevance = self.calculate_relevance(service_title, search_query)
            
            # Применяем базовый порог
            if relevance >= min_relevance:
                results.append((service, relevance))
        
        # Сортируем по релевантности (от большей к меньшей)
        results.sort(key=lambda x: x[1], reverse=True)
        
        # АДАПТИВНЫЙ ПОРОГ: если есть результаты и лучший результат высокий
        if results:
            best_score = results[0][1]
            
            # Если лучший результат очень хороший (>70), применяем динамический фильтр
            if best_score > 70.0:
                # Игнорируем результаты, которые значительно хуже лучшего (разница >15 баллов)
                adaptive_threshold = best_score - 15.0
                results = [
                    (service, score) for service, score in results 
                    if score >= adaptive_threshold
                ]
        
        # Возвращаем топ результатов
        return results[:max_results]
    
    def calculate_name_relevance(self, name: str, search_query: str) -> float:
        """
        Вычисляет релевантность имени к поисковому запросу
        
        Args:
            name: Имя для проверки
            search_query: Поисковый запрос
            
        Returns:
            Оценка релевантности (0-100)
        """
        if not name or not search_query:
            return 0.0
        
        # Нормализуем тексты
        normalized_name = self._normalize_text(name)
        normalized_query = self._normalize_text(search_query)
        
        # Точное совпадение
        if normalized_name == normalized_query:
            return 100.0
        
        # Нечеткое сравнение
        ratio = fuzz.ratio(normalized_name, normalized_query)
        partial_ratio = fuzz.partial_ratio(normalized_name, normalized_query)
        token_ratio = fuzz.token_sort_ratio(normalized_name, normalized_query)
        
        # Проверяем, содержится ли запрос в имени или наоборот
        query_in_name = normalized_query in normalized_name
        name_in_query = normalized_name in normalized_query
        
        # Базовая релевантность
        base_relevance = max(ratio, partial_ratio, token_ratio)
        
        # Бонусы за вхождение
        if query_in_name:
            base_relevance = max(base_relevance, 80.0)
        
        if name_in_query:
            base_relevance = max(base_relevance, 70.0)
        
        return min(base_relevance, 100.0)
    
    def find_best_masters(
        self,
        masters: List[Dict],
        master_name: str,
        min_relevance: float = 30.0,
        max_results: int = 15
    ) -> List[Tuple[Dict, float]]:
        """
        Находит наиболее релевантных мастеров по имени
        
        Args:
            masters: Список мастеров (словари с ключом 'name')
            master_name: Имя мастера для поиска
            min_relevance: Минимальная релевантность для включения в результат
            max_results: Максимальное количество результатов
            
        Returns:
            Список кортежей (мастер, релевантность), отсортированный по убыванию релевантности
        """
        results = []
        
        for master in masters:
            master_name_field = master.get('name', '')
            if not master_name_field or master_name_field == "Лист ожидания":
                continue
            
            # Вычисляем релевантность имени
            relevance = self.calculate_name_relevance(master_name_field, master_name)
            
            if relevance >= min_relevance:
                results.append((master, relevance))
        
        # Сортируем по релевантности (от большей к меньшей)
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Возвращаем топ результатов
        return results[:max_results]
