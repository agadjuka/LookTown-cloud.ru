"""
Модуль для умного поиска услуг с использованием морфологического анализа
"""
from typing import List, Tuple, Dict
from rapidfuzz import fuzz
import re

try:
    import pymorphy3
    MORPH_AVAILABLE = True
except ImportError:
    MORPH_AVAILABLE = False


class ServiceMatcher:
    """Класс для умного сопоставления услуг с поисковыми запросами"""
    
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
        
        Args:
            text: Текст для обработки
            
        Returns:
            Список ключевых слов
        """
        # Служебные слова, которые не важны для поиска
        stop_words = {
            "на", "для", "по", "с", "в", "к", "от", "до", "из", "у", "о", "об",
            "и", "или", "а", "но", "же", "ли", "бы", "то", "как", "что",
            "услуги", "услуга", "услуг", "услугу", "услуге", "услугой",
            "хочу", "нужен", "нужна", "нужно", "нужны",
            "записаться", "запись", "записи"
        }
        
        normalized = self._normalize_text(text)
        words = normalized.split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords
    
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
        
        # Извлекаем ключевые слова
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
        
        if query_in_title and all_keywords_found:
            # Запрос содержится в названии и все ключевые слова найдены - высокий приоритет
            base_relevance = max(base_relevance, 85.0)
        elif query_in_title:
            # Запрос содержится в названии, но не все ключевые слова - средний приоритет
            base_relevance = max(base_relevance, 50.0)
        
        if title_in_query:
            # Название содержится в запросе
            base_relevance = max(base_relevance, 40.0)
        
        # Фильтрация: если релевантность низкая и не все ключевые слова найдены - отбрасываем
        if base_relevance < 50.0:
            if not matched_keywords:
                return 0.0
            # Если есть совпадения, но релевантность низкая - возвращаем пропорционально
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
        
        Args:
            services: Список услуг (словари с ключом 'title' или 'name')
            search_query: Поисковый запрос
            min_relevance: Минимальная релевантность для включения в результат
            max_results: Максимальное количество результатов
            
        Returns:
            Список кортежей (услуга, релевантность), отсортированный по убыванию релевантности
        """
        results = []
        
        for service in services:
            # Получаем название услуги
            service_title = service.get('title', '') or service.get('name', '')
            if not service_title:
                continue
            
            # Вычисляем релевантность
            relevance = self.calculate_relevance(service_title, search_query)
            
            if relevance >= min_relevance:
                results.append((service, relevance))
        
        # Сортируем по релевантности (от большей к меньшей)
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Возвращаем топ результатов
        return results[:max_results]
