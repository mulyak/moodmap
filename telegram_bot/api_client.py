import requests
from typing import Dict, List, Any, Optional

def normalize_phone_number(phone_number):
    """
    Нормализует телефонный номер: удаляет все нецифровые символы (скобки, тире, плюсы и т.д.)
    
    Аргументы:
        phone_number: Исходный номер телефона
        
    Возвращает:
        Нормализованный номер телефона, содержащий только цифры, включая код страны
    """
    if not phone_number:
        return phone_number
    
    # Удаляем все нецифровые символы из номера телефона (включая скобки, тире, плюсы, пробелы и т.д.)
    normalized = ''.join(char for char in phone_number if char.isdigit())
    
    return normalized

class APIClient:
    """
    Клиент для взаимодействия с API Flask-приложения.
    Позволяет отправлять запросы к API и получать данные.
    """
    
    def __init__(self, base_url: str):
        """
        Инициализация клиента API с базовым URL.
        
        Аргументы:
            base_url: Базовый URL API (например, 'http://localhost:5000/api')
        """
        self.base_url = base_url.rstrip('/')  # Удаляем слеш в конце URL, если он есть
    
    def register_user(self, phone_number: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Регистрация нового пользователя в системе.
        
        Аргументы:
            phone_number: Номер телефона пользователя
            password: Пароль пользователя (если не указан, будет сгенерирован автоматически)
            
        Возвращает:
            Словарь с информацией о пользователе или сообщением об ошибке
        """
        url = f"{self.base_url}/auth/register"  # Полный URL для регистрации
        
        # Нормализуем номер телефона
        normalized_phone = normalize_phone_number(phone_number)
        
        data = {
            "phone_number": normalized_phone  # Данные для отправки на сервер
        }
        
        # Добавляем пароль в запрос, если он указан
        if password:
            data["password"] = password
        
        try:
            # Отправляем POST-запрос с JSON-данными
            response = requests.post(url, json=data)
            
            # Проверяем успешность ответа (коды 200-299)
            if not response.ok:
                try:
                    return response.json()  # Пытаемся получить JSON с ошибкой
                except:
                    # Если ответ не в формате JSON, создаем сообщение об ошибке на основе статус-кода
                    if response.status_code == 409:
                        return {"error": "Пользователь с таким номером телефона уже существует"}
                    else:
                        return {"error": f"Ошибка HTTP: {response.status_code}"}
            
            # Возвращаем данные успешного ответа
            return response.json()
        except requests.RequestException as e:
            # Обрабатываем сетевые ошибки (нет соединения и т.п.)
            return {"error": f"Сетевая ошибка: {str(e)}"}
    
    def login_user(self, phone_number: str, password: str) -> Dict[str, Any]:
        """
        Авторизация пользователя в системе.
        
        Аргументы:
            phone_number: Номер телефона пользователя
            password: Пароль пользователя
            
        Возвращает:
            Словарь с информацией о пользователе или сообщением об ошибке
        """
        url = f"{self.base_url}/auth/login"  # URL для авторизации
        
        # Нормализуем номер телефона
        normalized_phone = normalize_phone_number(phone_number)
        
        data = {
            "phone_number": normalized_phone,
            "password": password
        }
        
        try:
            # Отправляем POST-запрос с данными для входа
            response = requests.post(url, json=data)
            
            # Проверяем успешность ответа
            if not response.ok:
                try:
                    return response.json()  # Получаем JSON с ошибкой
                except:
                    # Формируем понятное сообщение об ошибке
                    if response.status_code == 401:
                        return {"error": "Неверные учетные данные"}
                    else:
                        return {"error": f"Ошибка HTTP: {response.status_code}"}
            
            # Возвращаем данные об успешном входе
            return response.json()
        except requests.RequestException as e:
            # Обрабатываем сетевые ошибки
            return {"error": f"Сетевая ошибка: {str(e)}"}
    
    def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        Получение информации о пользователе по его ID.
        
        Аргументы:
            user_id: ID пользователя в API
            
        Возвращает:
            Словарь с информацией о пользователе или сообщением об ошибке
        """
        url = f"{self.base_url}/user/{user_id}"  # URL для получения данных пользователя
        
        try:
            # Отправляем GET-запрос
            response = requests.get(url)
            return response.json()  # Возвращаем полученные данные
        except requests.RequestException as e:
            # В случае ошибки формируем сообщение
            return {"error": str(e)}
    
    def get_user_moods(self, user_id: int, lat: Optional[float] = None, 
                      lng: Optional[float] = None, radius: Optional[float] = None,
                      hours: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Получение списка настроений пользователя с возможностью фильтрации.
        
        Аргументы:
            user_id: ID пользователя в API
            lat: Широта для фильтрации по местоположению (необязательно)
            lng: Долгота для фильтрации по местоположению (необязательно)
            radius: Радиус в км для фильтрации по местоположению (необязательно)
            hours: Количество часов для фильтрации по времени (необязательно)
            
        Возвращает:
            Список словарей с данными о настроениях или пустой список при ошибке
        """
        url = f"{self.base_url}/user/{user_id}/moods"  # URL для получения настроений
        params = {}  # Параметры запроса
        
        # Добавляем параметры фильтрации, если они указаны
        if lat is not None:
            params['lat'] = lat
        if lng is not None:
            params['lng'] = lng
        if radius is not None:
            params['radius'] = radius
        if hours is not None:
            params['hours'] = hours
        
        try:
            # Отправляем GET-запрос с параметрами
            response = requests.get(url, params=params)
            return response.json()  # Возвращаем список настроений
        except requests.RequestException:
            # При ошибке возвращаем пустой список
            return []
    
    def create_mood(self, user_id: int, emoji: str, latitude: float, 
                   longitude: float, text: str = "") -> Dict[str, Any]:
        """
        Создание новой метки настроения.
        
        Аргументы:
            user_id: ID пользователя в API
            emoji: Эмодзи настроения
            latitude: Широта местоположения
            longitude: Долгота местоположения
            text: Текстовое описание настроения (необязательно)
            
        Возвращает:
            Словарь с данными созданного настроения или сообщением об ошибке
        """
        url = f"{self.base_url}/moods"  # URL для создания настроения
        data = {
            "user_id": user_id,
            "emoji": emoji,
            "latitude": latitude,
            "longitude": longitude,
            "text": text
        }
        
        try:
            # Отправляем POST-запрос с данными настроения
            response = requests.post(url, json=data)
            return response.json()  # Возвращаем результат операции
        except requests.RequestException as e:
            # Формируем сообщение об ошибке
            return {"error": str(e)}
    
    def delete_mood(self, mood_id: int, user_id: int) -> bool:
        """
        Удаление метки настроения.
        
        Аргументы:
            mood_id: ID настроения для удаления
            user_id: ID пользователя, которому принадлежит настроение
            
        Возвращает:
            True, если удаление успешно, False в случае ошибки
        """
        url = f"{self.base_url}/moods/{mood_id}"  # URL для удаления настроения
        params = {
            "user_id": user_id  # Параметры запроса
        }
        
        try:
            # Отправляем DELETE-запрос
            response = requests.delete(url, params=params)
            # Проверяем успешность операции по коду ответа
            return response.status_code in (200, 204)
        except requests.RequestException:
            # При ошибке запроса возвращаем False
            return False
    
    def get_area_mood(self, latitude: float, longitude: float, 
                     radius: float = 5.0, hours: Optional[int] = None) -> Dict[str, Any]:
        """
        Получение информации о настроении в определенной области.
        
        Аргументы:
            latitude: Широта центра области
            longitude: Долгота центра области
            radius: Радиус области в км (по умолчанию 5.0)
            hours: Количество часов для фильтрации по времени (необязательно)
            
        Возвращает:
            Словарь с информацией о настроении области или сообщением об ошибке
        """
        url = f"{self.base_url}/area-mood"  # URL для получения настроения области
        params = {
            "lat": latitude,
            "lng": longitude,
            "radius": radius
        }
        
        # Добавляем фильтр по времени, если указан
        if hours is not None:
            params["hours"] = hours
        
        try:
            # Отправляем GET-запрос с параметрами
            response = requests.get(url, params=params)
            return response.json()  # Возвращаем данные о настроении
        except requests.RequestException as e:
            # Формируем сообщение об ошибке
            return {"error": str(e)}
    
    def get_trends(self, latitude: Optional[float] = None, longitude: Optional[float] = None,
                  radius: Optional[float] = None, hours: int = 24) -> Dict[str, Any]:
        """
        Получение трендов настроений.
        
        Аргументы:
            latitude: Широта центра области (необязательно)
            longitude: Долгота центра области (необязательно)
            radius: Радиус области в км (необязательно)
            hours: Количество часов для анализа (по умолчанию 24)
            
        Возвращает:
            Словарь с информацией о трендах настроений или сообщением об ошибке
        """
        url = f"{self.base_url}/trends"  # URL для получения трендов
        params = {
            "hours": hours
        }
        
        # Добавляем параметры местоположения, если они указаны
        if latitude is not None:
            params["lat"] = latitude
        if longitude is not None:
            params["lng"] = longitude
        if radius is not None:
            params["radius"] = radius
        
        try:
            # Отправляем GET-запрос с параметрами
            response = requests.get(url, params=params)
            return response.json()  # Возвращаем данные о трендах
        except requests.RequestException as e:
            # Формируем сообщение об ошибке
            return {"error": str(e)}
    
    def get_events(self, latitude: Optional[float] = None, longitude: Optional[float] = None,
                  radius: Optional[float] = None, hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Получение информации о событиях.
        
        Аргументы:
            latitude: Широта центра области (необязательно)
            longitude: Долгота центра области (необязательно)
            radius: Радиус области в км (необязательно)
            hours: Количество часов для фильтрации (необязательно, по умолчанию 24)
            
        Возвращает:
            Список словарей с информацией о событиях или пустой список при ошибке
        """
        url = f"{self.base_url}/events"  # URL для получения событий
        params = {}
        
        # Добавляем параметры запроса, если они указаны
        if latitude is not None:
            params["lat"] = latitude
        if longitude is not None:
            params["lng"] = longitude
        if radius is not None:
            params["radius"] = radius
        if hours is not None:
            params["hours"] = hours
        
        try:
            # Отправляем GET-запрос с параметрами
            response = requests.get(url, params=params)
            return response.json()  # Возвращаем список событий
        except requests.RequestException:
            # При ошибке возвращаем пустой список
            return [] 