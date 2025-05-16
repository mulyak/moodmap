import math
from datetime import datetime, timedelta
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional


class MoodAnalyzer:
    """Класс для анализа данных о настроениях и обнаружения событий."""
    
    # Константы для анализа
    CLUSTER_RADIUS_KM = 1.0  # Радиус для кластеризации настроений в километрах
    TIME_WINDOW_HOURS = 4    # Временное окно для рассмотрения настроений как части одного события
    MIN_CLUSTER_SIZE = 5     # Минимальное количество настроений для формирования кластера
    
    # Категории эмодзи
    POSITIVE_EMOJIS = ['😊', '😎', '🥰']
    NEGATIVE_EMOJIS = ['😢', '😡', '😷']
    NEUTRAL_EMOJIS = ['😐', '🤔', '😴']
    
    # Ключевые слова для обнаружения событий
    EVENT_KEYWORDS = {
        'concert': ['концерт', 'музыка', 'группа', 'шоу', 'выступление'],
        'sports': ['игра', 'матч', 'спорт', 'команда', 'победа', 'проигрыш'],
        'traffic': ['пробка', 'затор', 'авария', 'дорога', 'машина'],
        'weather': ['дождь', 'снег', 'жара', 'холод', 'погода', 'гроза'],
        'food': ['ресторан', 'еда', 'покушать', 'ужин', 'обед'],
        'party': ['вечеринка', 'праздник', 'день рождения', 'юбилей']
    }
    
    def __init__(self, moods: List[Dict[str, Any]]):
        """Инициализация анализатора с данными о настроениях.
        
        Аргументы:
            moods: Список словарей настроений с ключами:
                - id: Уникальный идентификатор
                - emoji: Эмодзи настроения
                - text: Опциональное текстовое описание
                - latitude: Географическая широта
                - longitude: Географическая долгота
                - timestamp: Время создания настроения
                - user_id: ID пользователя, создавшего настроение
        """
        self.moods = moods
    
    def cluster_moods(self) -> List[Dict[str, Any]]:
        """Группировка настроений по географической близости и временному окну.
        
        Эта функция объединяет настроения в группы (кластеры), если они:
        1. Находятся близко друг к другу географически
        2. Созданы в близкий временной промежуток
        
        Возвращает:
            Список кластеров, где каждый кластер - словарь с:
                - center: (lat, lng) координаты центра кластера
                - moods: Список настроений в кластере
                - dominant_emoji: Самый частый эмодзи в кластере
                - mood_percentage: Процент положительных настроений (0-100)
        """
        # Список для хранения найденных кластеров
        clusters = []
        # Множество для отслеживания уже обработанных настроений
        processed_ids = set()
        
        # Сортировка настроений по временной метке (сначала новые)
        sorted_moods = sorted(
            self.moods, 
            key=lambda m: datetime.fromisoformat(m['timestamp']), 
            reverse=True
        )
        
        # Перебираем все настроения для формирования кластеров
        for mood in sorted_moods:
            # Пропускаем уже обработанные настроения
            if mood['id'] in processed_ids:
                continue
                
            # Начинаем новый кластер с этого настроения
            cluster_moods = [mood]
            processed_ids.add(mood['id'])
            
            # Запоминаем время и местоположение первого настроения в кластере
            mood_time = datetime.fromisoformat(mood['timestamp'])
            mood_location = (mood['latitude'], mood['longitude'])
            
            # Находим другие настроения, принадлежащие этому кластеру
            for other_mood in sorted_moods:
                # Пропускаем уже обработанные настроения
                if other_mood['id'] in processed_ids:
                    continue
                    
                # Получаем время и местоположение проверяемого настроения
                other_time = datetime.fromisoformat(other_mood['timestamp'])
                other_location = (other_mood['latitude'], other_mood['longitude'])
                
                # Проверяем, находится ли настроение в пределах временного окна и радиуса расстояния
                time_diff = abs((mood_time - other_time).total_seconds() / 3600)  # разница в часах
                distance = self._calculate_distance(
                    mood_location[0], mood_location[1],
                    other_location[0], other_location[1]
                )
                
                # Если настроение подходит по времени и расстоянию, добавляем его в кластер
                if time_diff <= self.TIME_WINDOW_HOURS and distance <= self.CLUSTER_RADIUS_KM:
                    cluster_moods.append(other_mood)
                    processed_ids.add(other_mood['id'])
            
            # Рассматриваем только кластеры с достаточным количеством настроений
            if len(cluster_moods) >= self.MIN_CLUSTER_SIZE:
                # Вычисляем центр кластера (среднее местоположение всех настроений)
                lat_sum = sum(m['latitude'] for m in cluster_moods)
                lng_sum = sum(m['longitude'] for m in cluster_moods)
                center = (lat_sum / len(cluster_moods), lng_sum / len(cluster_moods))
                
                # Находим самый популярный эмодзи в кластере
                emoji_counter = Counter(m['emoji'] for m in cluster_moods)
                dominant_emoji = emoji_counter.most_common(1)[0][0]
                
                # Вычисляем процент положительного настроения в кластере
                mood_percentage = self._calculate_mood_percentage(cluster_moods)
                
                # Добавляем кластер в результат
                clusters.append({
                    'center': center,
                    'moods': cluster_moods,
                    'dominant_emoji': dominant_emoji,
                    'mood_percentage': mood_percentage
                })
        
        return clusters
    
    def detect_events(self) -> List[Dict[str, Any]]:
        """Обнаружение вероятных событий на основе кластеров настроений.
        
        Анализирует кластеры настроений и пытается определить,
        соответствуют ли они каким-либо событиям (концерт, спортивное
        мероприятие и т.д.) на основе ключевых слов в текстах.
        
        Возвращает:
            Список обнаруженных событий, где каждое событие - словарь с:
                - location: (lat, lng) координаты центра события
                - type: Тип события (или 'unknown' если не определен)
                - confidence: Оценка уверенности в определении (0-100)
                - dominant_emoji: Самый частый эмодзи события
                - mood_percentage: Процент положительных настроений (0-100)
                - moods_count: Количество настроений в кластере события
                - keywords: Список найденных ключевых слов
        """
        # Получаем кластеры настроений
        clusters = self.cluster_moods()
        # Список для хранения обнаруженных событий
        events = []
        
        # Анализируем каждый кластер
        for cluster in clusters:
            # Собираем весь текст из настроений в кластере в одну строку
            all_text = ' '.join(m['text'].lower() for m in cluster['moods'] if m.get('text'))
            
            # Определяем тип события на основе ключевых слов в тексте
            event_type, keywords, confidence = self._detect_event_type(all_text)
            
            # Включаем только события с достаточной уверенностью
            if confidence >= 30:
                events.append({
                    'location': cluster['center'],
                    'type': event_type,
                    'confidence': confidence,
                    'dominant_emoji': cluster['dominant_emoji'],
                    'mood_percentage': cluster['mood_percentage'],
                    'moods_count': len(cluster['moods']),
                    'keywords': keywords
                })
        
        return events
    
    def get_area_mood(self, lat: float, lng: float, radius_km: float = 5.0) -> Dict[str, Any]:
        """Получение общего настроения для конкретной географической области.
        
        Анализирует настроения, которые находятся в пределах указанного радиуса
        от заданной точки, и определяет общее настроение этой области.
        
        Аргументы:
            lat: Широта центральной точки области
            lng: Долгота центральной точки области
            radius_km: Радиус в километрах для рассмотрения
            
        Возвращает:
            Словарь с информацией о настроении области:
                - dominant_emoji: Преобладающий эмодзи в области
                - mood_percentage: Процент положительных настроений (0-100)
                - moods_count: Количество настроений в области
        """
        # Находим настроения в пределах указанного радиуса
        area_moods = []
        for mood in self.moods:
            # Вычисляем расстояние между точкой и настроением
            distance = self._calculate_distance(
                lat, lng, mood['latitude'], mood['longitude']
            )
            # Добавляем настроение, если оно в пределах радиуса
            if distance <= radius_km:
                area_moods.append(mood)
        
        # Если в этой области нет настроений, возвращаем нейтральное
        if not area_moods:
            return {
                'dominant_emoji': '😐',
                'mood_percentage': 50,
                'moods_count': 0
            }
        
        # Находим преобладающий эмодзи
        emoji_counter = Counter(m['emoji'] for m in area_moods)
        dominant_emoji = emoji_counter.most_common(1)[0][0] if emoji_counter else '😐'
        
        # Вычисляем процент положительных настроений
        mood_percentage = self._calculate_mood_percentage(area_moods)
        
        # Возвращаем информацию о настроении области
        return {
            'dominant_emoji': dominant_emoji,
            'mood_percentage': mood_percentage,
            'moods_count': len(area_moods)
        }
    
    def get_mood_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Получение трендов изменения настроений за указанный период времени.
        
        Анализирует, как менялись настроения с течением времени,
        и предоставляет статистику за указанный период.
        
        Аргументы:
            hours: Количество часов для анализа (по умолчанию 24 часа)
            
        Возвращает:
            Словарь с информацией о трендах:
                - time_periods: Список периодов времени
                - mood_percentages: Список процентов положительных настроений по периодам
                - emoji_counts: Словарь с количеством разных эмодзи
                - trend_direction: Направление изменения настроения ('up', 'down', или 'stable')
        """
        # Получаем текущее время
        now = datetime.utcnow()
        # Разбиваем период на 6 временных интервалов
        period_hours = hours / 6
        time_periods = []
        mood_percentages = []
        
        # Для каждого временного интервала собираем данные
        for i in range(6):
            # Определяем границы временного интервала
            period_end = now - timedelta(hours=i * period_hours)
            period_start = now - timedelta(hours=(i + 1) * period_hours)
            
            # Фильтруем настроения, попадающие в этот интервал
            period_moods = []
            for mood in self.moods:
                mood_time = datetime.fromisoformat(mood['timestamp'])
                if period_start <= mood_time <= period_end:
                    period_moods.append(mood)
            
            # Если в интервале есть настроения, вычисляем процент положительных
            if period_moods:
                mood_percentage = self._calculate_mood_percentage(period_moods)
            else:
                mood_percentage = 0
            
            # Форматируем временной интервал для отображения
            time_periods.append(f"{period_start.strftime('%H:%M')} - {period_end.strftime('%H:%M')}")
            mood_percentages.append(mood_percentage)
        
        # Подсчитываем количество каждого эмодзи
        emoji_counts = {}
        for mood in self.moods:
            emoji = mood['emoji']
            emoji_counts[emoji] = emoji_counts.get(emoji, 0) + 1
        
        # Определяем направление тренда (растет, падает или стабилен)
        trend_direction = 'stable'  # по умолчанию стабильный
        if len(mood_percentages) >= 2:
            # Если последнее значение больше предыдущего, тренд растет
            if mood_percentages[0] > mood_percentages[1]:
                trend_direction = 'up'
            # Если последнее значение меньше предыдущего, тренд падает
            elif mood_percentages[0] < mood_percentages[1]:
                trend_direction = 'down'
        
        # Формируем результат
        return {
            'time_periods': time_periods,
            'mood_percentages': mood_percentages,
            'emoji_counts': emoji_counts,
            'trend_direction': trend_direction
        }
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Расчет расстояния между двумя географическими точками в километрах.
        
        Использует формулу гаверсинусов для вычисления расстояния 
        между двумя точками на поверхности Земли.
        
        Аргументы:
            lat1: Широта первой точки
            lon1: Долгота первой точки
            lat2: Широта второй точки
            lon2: Долгота второй точки
            
        Возвращает:
            Расстояние в километрах
        """
        # Радиус Земли в километрах
        R = 6371.0
        
        # Перевод координат из градусов в радианы
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Разницы в координатах
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        
        # Формула гаверсинусов
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        
        return distance
    
    def _calculate_mood_percentage(self, moods: List[Dict[str, Any]]) -> int:
        """Вычисление процента положительных настроений в списке.
        
        Анализирует эмодзи в списке настроений и определяет,
        какой процент из них считается "положительным".
        
        Аргументы:
            moods: Список настроений для анализа
            
        Возвращает:
            Процент положительных настроений от 0 до 100
        """
        if not moods:
            return 50  # Нейтральное значение, если нет данных
        
        # Подсчет положительных, отрицательных и нейтральных эмодзи
        positive_count = sum(1 for m in moods if m['emoji'] in self.POSITIVE_EMOJIS)
        negative_count = sum(1 for m in moods if m['emoji'] in self.NEGATIVE_EMOJIS)
        neutral_count = sum(1 for m in moods if m['emoji'] in self.NEUTRAL_EMOJIS)
        
        # Общее количество настроений
        total = positive_count + negative_count + neutral_count
        
        # Если нет настроений с определенным эмодзи, возвращаем 50%
        if total == 0:
            return 50
        
        # Вычисляем процент положительных настроений
        # Нейтральные настроения считаются наполовину положительными
        return int((positive_count + neutral_count / 2) / total * 100)
    
    def _detect_event_type(self, text: str) -> Tuple[str, List[str], int]:
        """Определение типа события на основе текста.
        
        Анализирует текст на наличие ключевых слов, связанных
        с разными типами событий (концерт, спорт и т.д.).
        
        Аргументы:
            text: Текст для анализа
            
        Возвращает:
            Кортеж из трех элементов:
                - Тип события (или 'unknown' если не определен)
                - Список найденных ключевых слов
                - Оценка уверенности (от 0 до 100)
        """
        # Если текст пустой, не можем определить тип события
        if not text:
            return 'unknown', [], 0
        
        # Для каждого типа события подсчитываем количество найденных ключевых слов
        event_scores = {}
        found_keywords = {}
        
        for event_type, keywords in self.EVENT_KEYWORDS.items():
            found_keywords[event_type] = []
            
            # Проверяем каждое ключевое слово
            for keyword in keywords:
                if keyword in text:
                    found_keywords[event_type].append(keyword)
            
            # Вычисляем "балл" для этого типа события
            event_scores[event_type] = len(found_keywords[event_type])
        
        # Если нет ключевых слов, не можем определить тип события
        if all(score == 0 for score in event_scores.values()):
            return 'unknown', [], 0
        
        # Находим тип события с наибольшим количеством ключевых слов
        best_event_type = max(event_scores, key=event_scores.get)
        best_score = event_scores[best_event_type]
        best_keywords = found_keywords[best_event_type]
        
        # Вычисляем уверенность в определении (от 0 до 100)
        # Максимальная уверенность, если найдены все ключевые слова для типа
        max_score = len(self.EVENT_KEYWORDS[best_event_type])
        confidence = int(min(best_score / max_score * 100 + 20, 100))
        
        return best_event_type, best_keywords, confidence 