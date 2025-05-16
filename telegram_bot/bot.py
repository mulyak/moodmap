import os
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    ConversationHandler, CallbackContext, CallbackQueryHandler
)
from telegram.error import TelegramError
from api_client import APIClient, normalize_phone_number
import requests
import time

from models import UserRepository

# Загружаем переменные окружения из файла .env
load_dotenv()

# Настраиваем логирование для отслеживания работы бота
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщений лога
    level=logging.INFO  # Уровень логирования
)
logger = logging.getLogger(__name__)  # Создаем объект логгера для текущего модуля

# Получаем настройки из переменных окружения
# TOKEN - ключ для доступа к API Telegram (получается у @BotFather)
# API_BASE_URL - адрес, по которому доступен API нашего веб-приложения
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # Получаем токен из переменных окружения
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:5000/api")  # URL API с дефолтным значением

# Инициализируем API-клиент для взаимодействия с нашим веб-сервером
# API-клиент позволяет обмениваться данными между ботом и основным приложением
api_client = APIClient(API_BASE_URL)

# Определяем состояния для диалога с пользователем
# ConversationHandler использует эти состояния для управления диалогом
# Каждое состояние соответствует определенному этапу взаимодействия с пользователем
(
    START,             # Начальное состояние, когда пользователь запускает бота
    PHONE_NUMBER,      # Состояние ожидания ввода номера телефона
    PASSWORD,          # Состояние ожидания ввода пароля
    MAIN_MENU,         # Главное меню бота
    MOOD_EMOJI,        # Выбор эмодзи для настроения
    MOOD_TEXT,         # Ввод текстового описания настроения
    MOOD_LOCATION,     # Отправка местоположения для настроения
    PROFILE,           # Просмотр профиля пользователя
    VIEW_MOODS,        # Просмотр настроений пользователя
    DELETE_MOOD,       # Удаление настроения
    AREA_MOOD,         # Просмотр настроений в области
    AREA_RADIUS,       # Установка радиуса для просмотра настроений
    AREA_HOURS,        # Установка временного диапазона для просмотра настроений
    TRENDS,            # Просмотр трендов настроений
    EVENTS             # Просмотр событий, определенных по настроениям
) = range(15)  # Создаем 15 последовательных целых чисел для состояний диалога

# Список доступных эмодзи для выбора настроения
# Пользователь выбирает один из этих эмодзи для обозначения своего настроения
EMOJI_OPTIONS = ["😊", "😎", "🥰", "😐", "🤔", "😴", "😢", "😡", "😷"]

# Глобальная переменная для хранения экземпляра notifier
event_notifier = None

# Вспомогательные функции для создания клавиатур
def get_main_menu_keyboard():
    """
    Создание клавиатуры главного меню.
    
    Клавиатура в Telegram - это набор кнопок, которые отображаются у пользователя
    и позволяют ему взаимодействовать с ботом без ввода текста.
    
    Возвращает:
        Объект ReplyKeyboardMarkup с кнопками главного меню
    """
    keyboard = [
        [KeyboardButton("📝 Создать метку настроения")],  # Первый ряд с одной кнопкой
        [KeyboardButton("👤 Профиль"), KeyboardButton("🔍 Настроение вокруг меня")],  # Второй ряд с двумя кнопками
        [KeyboardButton("📊 Тренды"), KeyboardButton("🎭 События")]  # Третий ряд с двумя кнопками
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  # resize_keyboard делает кнопки меньше по размеру

def get_emoji_keyboard():
    """
    Создание клавиатуры с эмодзи для выбора настроения.
    
    Эта функция создает клавиатуру, на которой пользователь может выбрать эмодзи,
    соответствующий его текущему настроению.
    
    Возвращает:
        Объект ReplyKeyboardMarkup с кнопками-эмодзи
    """
    keyboard = []
    row = []
    # Формируем сетку кнопок с эмодзи (по 3 в ряд)
    for i, emoji in enumerate(EMOJI_OPTIONS):
        row.append(KeyboardButton(emoji))
        if (i + 1) % 3 == 0:  # Формируем по 3 эмодзи в ряд
            keyboard.append(row)
            row = []
    if row:  # Если остались непомещенные кнопки
        keyboard.append(row)
    keyboard.append([KeyboardButton("❌ Отмена")])  # Добавляем кнопку отмены внизу
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_location_keyboard(telegram_id=None):
    """
    Создание клавиатуры с кнопкой отправки геолокации.
    
    Telegram позволяет запрашивать геолокацию пользователя через специальную кнопку.
    Эта функция создает клавиатуру с такой кнопкой.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram (для проверки наличия последней метки)
    
    Возвращает:
        Объект ReplyKeyboardMarkup с кнопкой запроса местоположения
    """
    keyboard = [
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],  # Кнопка запроса местоположения
    ]
    
    # Если указан ID пользователя, проверяем наличие последней метки
    if telegram_id and UserRepository.is_last_location_valid(telegram_id):
        keyboard.insert(0, [KeyboardButton("🔄 Последняя геолокация")])
        
    keyboard.append([KeyboardButton("❌ Отмена")])  # Кнопка отмены
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_api_credentials(telegram_id: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Получение учетных данных пользователя для доступа к API.
    
    Эта функция проверяет, есть ли пользователь в базе данных и возвращает его ID в API.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram
    
    Возвращает:
        Кортеж из ID пользователя в API и пароля (если сохранен в контексте)
    """
    try:
        # Получаем информацию о пользователе из базы данных
        user = UserRepository.get_user_by_telegram_id(telegram_id)
        if not user:
            return None, None
        
        # Возвращаем ID пользователя в API
        return user.get('api_user_id'), None
    except Exception as e:
        logger.error(f"Ошибка при получении учетных данных: {e}")
        return None, None

def update_user_location(telegram_id: int, latitude: float, longitude: float):
    """
    Обновление местоположения пользователя.
    
    Эта функция сохраняет или обновляет местоположение пользователя в базе данных.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram
        latitude: Широта местоположения
        longitude: Долгота местоположения
    """
    try:
        # Обновляем местоположение пользователя в базе данных
        UserRepository.update_user_location(telegram_id, latitude, longitude)
    except Exception as e:
        logger.error(f"Ошибка при обновлении местоположения пользователя {telegram_id}: {e}")

def create_mood_with_api(telegram_id: int, emoji: str, latitude: float, longitude: float, text: str = "", context=None) -> Dict[str, Any]:
    """
    Создание новой метки настроения через API.
    
    Эта функция отправляет данные о новом настроении пользователя на сервер через API.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram
        emoji: Эмодзи, отражающее настроение
        latitude: Широта местоположения
        longitude: Долгота местоположения
        text: Текстовое описание настроения (необязательно)
        context: Контекст диалога с паролем
    
    Возвращает:
        Словарь с данными созданного настроения или сообщением об ошибке
    """
    # Получаем ID пользователя в API
    api_user_id, _ = get_user_api_credentials(telegram_id)
    
    if not api_user_id:
        return {"error": "Вы не авторизованы. Пожалуйста, начните с /start"}
    
    # Сначала авторизуемся с сохраненными данными
    user = UserRepository.get_user_by_telegram_id(telegram_id)
    if not user or not user.get('phone_number'):
        return {"error": "Отсутствует номер телефона. Пожалуйста, начните с /start"}
    
    # Получаем пароль из контекста пользователя (временный пароль для текущей сессии)
    password = context.user_data.get('api_password') if context else None
    if not password:
        return {"error": "Для этого действия требуется авторизация. Пожалуйста, перезапустите бота командой /start и введите пароль."}
        
    # Логинимся для получения актуальной информации о пользователе
    login_response = api_client.login_user(user['phone_number'], password)
    if 'error' in login_response:
        return login_response
    
    # Обновляем местоположение пользователя в базе данных
    update_user_location(telegram_id, latitude, longitude)
    
    # Обновляем время последней метки настроения
    UserRepository.update_mood_location_time(telegram_id, latitude, longitude)
    
    # Создаем настроение через API
    return api_client.create_mood(api_user_id, emoji, latitude, longitude, text)

def delete_mood_with_api(telegram_id: int, mood_id: int, context=None) -> bool:
    """
    Удаление метки настроения через API.
    
    Эта функция удаляет ранее созданную метку настроения пользователя через API.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram
        mood_id: ID настроения для удаления
        context: Контекст диалога с паролем
    
    Возвращает:
        True, если удаление выполнено успешно, иначе False
    """
    # Получаем ID пользователя в API
    api_user_id, _ = get_user_api_credentials(telegram_id)
    
    if not api_user_id:
        return False
    
    # Сначала авторизуемся с сохраненными данными
    user = UserRepository.get_user_by_telegram_id(telegram_id)
    if not user or not user.get('phone_number'):
        return False
    
    # Получаем пароль из контекста пользователя (временный пароль для текущей сессии)
    password = context.user_data.get('api_password') if context else None
    if not password:
        return False
    
    # Логинимся для получения актуальной информации о пользователе
    login_response = api_client.login_user(user['phone_number'], password)
    if 'error' in login_response:
        return False
    
    # Удаляем настроение через API
    return api_client.delete_mood(mood_id, api_user_id)

# Функция для аутентификации и получения данных от API
def get_api_data_with_auth(telegram_id: int, api_method, context=None, **params):
    """
    Вызов метода API с авторизацией.
    
    Эта функция автоматически выполняет авторизацию и вызывает нужный
    метод API с переданными параметрами. Она упрощает работу с API,
    автоматически обрабатывая авторизацию.
    
    Аргументы:
        telegram_id: ID пользователя в Telegram
        api_method: Функция API-клиента для вызова
        context: Контекст диалога с паролем
        **params: Дополнительные параметры для метода API
    
    Возвращает:
        Данные, полученные от API, или сообщение об ошибке
    """
    # Получаем ID пользователя в API
    api_user_id, _ = get_user_api_credentials(telegram_id)
    
    if not api_user_id:
        return {"error": "Вы не авторизованы. Пожалуйста, начните с /start"}
    
    # Логинимся с сохраненными данными
    user = UserRepository.get_user_by_telegram_id(telegram_id)
    if not user or not user.get('phone_number'):
        return {"error": "Отсутствует номер телефона. Пожалуйста, начните с /start"}
    
    # Получаем пароль из контекста пользователя
    password = context.user_data.get('api_password') if context else None
    if not password:
        return {"error": "Для этого действия требуется авторизация. Пожалуйста, перезапустите бота командой /start и введите пароль."}
    
    # Выполняем логин для проверки актуальности учетных данных
    login_response = api_client.login_user(user['phone_number'], password)
    if 'error' in login_response:
        return login_response
    
    # Вызываем нужный метод API с переданными параметрами
    return api_method(**params)

def get_address_from_coordinates(latitude: float, longitude: float) -> str:
    """
    Получение адреса по координатам с использованием OpenStreetMap Nominatim API.
    
    Аргументы:
        latitude: Широта
        longitude: Долгота
        
    Возвращает:
        Строку с адресом или пустую строку в случае ошибки
    """
    try:
        # Добавляем задержку, чтобы не превысить лимит запросов к API (1 запрос в секунду)
        time.sleep(1)
        
        # Формируем URL для запроса к Nominatim API
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=18&addressdetails=1"
        
        # Добавляем User-Agent, чтобы соответствовать требованиям Nominatim API
        headers = {
            "User-Agent": "MoodMapBot/1.0"
        }
        
        # Отправляем запрос
        response = requests.get(url, headers=headers)
        
        # Проверяем успешность запроса
        if response.status_code == 200:
            data = response.json()
            
            # Получаем адрес из ответа
            if "display_name" in data:
                # Полный адрес может быть слишком длинным, поэтому возьмем только основную информацию
                address_parts = []
                address = data.get("address", {})
                
                # Собираем компоненты адреса в порядке от более конкретного к более общему
                if "road" in address:
                    address_parts.append(address["road"])
                if "house_number" in address:
                    address_parts.append(address["house_number"])
                if "suburb" in address:
                    address_parts.append(address["suburb"])
                if "city_district" in address:
                    address_parts.append(address["city_district"])
                if "city" in address:
                    address_parts.append(address["city"])
                
                # Если не удалось получить детальный адрес, используем общее название
                if not address_parts and "display_name" in data:
                    return data["display_name"]
                
                # Формируем строку адреса
                return ", ".join(address_parts)
        
        return ""
    except Exception as e:
        logger.error(f"Ошибка при получении адреса: {e}")
        return ""

# Обработчики команд
def start(update: Update, context: CallbackContext) -> int:
    """
    Начало диалога с ботом при команде /start.
    
    Это первая функция, которая вызывается, когда пользователь начинает взаимодействие с ботом.
    Она проверяет, зарегистрирован ли пользователь, и запрашивает номер телефона,
    если пользователь не найден в базе.
    
    Аргументы:
        update: Объект с данными от Telegram (содержит информацию о сообщении и пользователе)
        context: Контекст диалога (содержит данные, сохраняемые между вызовами обработчиков)
    
    Возвращает:
        Следующее состояние диалога (MAIN_MENU или PHONE_NUMBER)
    """
    try:
        # Получаем объект пользователя и его Telegram ID
        user = update.effective_user  # Объект с информацией о пользователе
        telegram_id = user.id  # Уникальный ID пользователя в Telegram
        
        # Проверяем, существует ли пользователь в нашей базе данных
        existing_user = UserRepository.get_user_by_telegram_id(telegram_id)
        
        # Если пользователь уже зарегистрирован и у него есть номер телефона и ID в API
        if existing_user and existing_user.get('phone_number') and existing_user.get('api_user_id'):
            # Пытаемся восстановить пароль для API-запросов
            # Запрашиваем пароль у пользователя, если он не был сохранен в контексте
            if not context.user_data.get('api_password'):
                # Запрашиваем пароль у пользователя
                update.message.reply_text(
                    f"Здравствуйте, {user.first_name}! Для продолжения работы с ботом, пожалуйста, введите ваш пароль:",
                    reply_markup=ReplyKeyboardRemove()
                )
                # Сохраняем номер телефона в контексте для последующей авторизации
                context.user_data['phone_number'] = existing_user.get('phone_number')
                context.user_data['is_new_user'] = False
                return PASSWORD
            
            # Переходим сразу в главное меню
            update.message.reply_text(
                f"Здравствуйте, {user.first_name}! Вы уже зарегистрированы.",
                reply_markup=get_main_menu_keyboard()  # Отображаем клавиатуру главного меню
            )
            return MAIN_MENU  # Возвращаем следующее состояние диалога - MAIN_MENU
        
        # Создаем запись пользователя, если её не существует
        if not existing_user:
            UserRepository.create_user(
                telegram_id=telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
        
        # Запрашиваем номер телефона с помощью специальной клавиатуры
        keyboard = [
            [KeyboardButton("📱 Отправить номер телефона", request_contact=True)]  # Кнопка запроса контакта
        ]
        # Создаем клавиатуру с кнопкой запроса контакта
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        # Отправляем приветственное сообщение и запрашиваем номер телефона
        update.message.reply_text(
            "Добро пожаловать в MoodMap Bot! 👋\n\n"
            "Для использования бота необходимо поделиться номером телефона для авторизации.",
            reply_markup=reply_markup
        )
        
        # Возвращаем следующее состояние диалога - PHONE_NUMBER
        return PHONE_NUMBER
    except Exception as e:
        # Обрабатываем возможные ошибки
        logger.error(f"Ошибка в обработчике start: {e}")
        update.message.reply_text(
            "Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=ReplyKeyboardRemove()  # Удаляем клавиатуру
        )
        return ConversationHandler.END  # Завершаем диалог

def phone_number(update: Update, context: CallbackContext) -> int:
    """
    Обработка полученного номера телефона и запрос пароля.
    
    Эта функция вызывается после того, как пользователь отправил свой номер телефона.
    Она сохраняет номер телефона и запрашивает пароль для авторизации.
    
    Аргументы:
        update: Объект с данными от Telegram
        context: Контекст диалога
        
    Возвращает:
        Следующее состояние диалога (PASSWORD или PHONE_NUMBER)
    """
    try:
        user = update.effective_user  # Получаем информацию о пользователе
        
        # Проверяем, есть ли в сообщении контакт или текст (но не кнопка "Отправить номер телефона")
        if update.message.contact or (update.message.text and update.message.text != "📱 Отправить номер телефона"):
            # Получаем номер телефона из контакта или текста сообщения
            if update.message.contact:
                phone_number = update.message.contact.phone_number  # Из объекта контакта
            else:
                # Если пользователь ввел номер телефона вручную текстом
                phone_number = update.message.text
                
            # Пытаемся удалить сообщение с контактом для безопасности
            # (чтобы номер телефона не оставался в истории чата)
            try:
                update.message.delete()
            except:
                logger.warning("Не удалось удалить сообщение с номером телефона")
            
            # Нормализуем номер телефона (убираем все лишние символы: скобки, дефисы, пробелы)
            phone_number = normalize_phone_number(phone_number)
            
            # Проверяем корректность номера телефона (должен содержать не менее 10 цифр)
            if not phone_number or len(phone_number) < 10:
                # Если номер некорректный, запрашиваем его снова
                update.message.reply_text(
                    "Пожалуйста, введите корректный номер телефона. Он должен содержать не менее 10 цифр.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]],
                                                   resize_keyboard=True, one_time_keyboard=True)
                )
                return PHONE_NUMBER  # Возвращаемся в состояние ожидания ввода номера телефона
            
            # Сохраняем номер телефона в данных пользователя для последующего использования
            context.user_data['phone_number'] = phone_number
            
            # Обновляем номер телефона пользователя в нашей базе данных
            UserRepository.update_user(
                user.id,
                phone_number=phone_number
            )
            
            # Проверяем, существует ли пользователь в API
            # Отправляем запрос на регистрацию без пароля и проверяем код ответа
            # Если ответ содержит ошибку "уже существует", значит пользователь существует
            response = api_client.register_user(phone_number)
            user_exists = isinstance(response, dict) and 'error' in response and 'уже существует' in response.get('error', '')
            
            if user_exists:
                # Если пользователь существует, запрашиваем пароль для входа
                update.message.reply_text(
                    "Пользователь с таким номером телефона уже существует. Пожалуйста, введите ваш пароль:",
                    reply_markup=ReplyKeyboardRemove()  # Удаляем клавиатуру
                )
                # Устанавливаем флаг, что это существующий пользователь (для функции password)
                context.user_data['is_new_user'] = False
            else:
                # Если пользователь новый, запрашиваем ввод нового пароля
                update.message.reply_text(
                    "Вы новый пользователь! Пожалуйста, придумайте и введите пароль для вашей учетной записи:",
                    reply_markup=ReplyKeyboardRemove()  # Удаляем клавиатуру
                )
                
                # Сохраняем флаг, что это новый пользователь (для функции password)
                context.user_data['is_new_user'] = True
                
            # Переходим в состояние ожидания ввода пароля
            return PASSWORD
        else:
            # Если пользователь не отправил контакт или ввел текст кнопки, запрашиваем снова
            update.message.reply_text(
                "Пожалуйста, поделитесь своим номером телефона, используя кнопку ниже или введите его вручную.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]],
                                                resize_keyboard=True, one_time_keyboard=True)
            )
            return PHONE_NUMBER  # Остаемся в состоянии ожидания ввода номера телефона
    except Exception as e:
        # Обрабатываем возможные ошибки
        logger.error(f"Ошибка в обработчике phone_number: {e}")
        update.message.reply_text(
            "Произошла ошибка при обработке номера телефона. Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()  # Удаляем клавиатуру
        )
        return ConversationHandler.END  # Завершаем диалог

def password(update: Update, context: CallbackContext) -> int:
    """Handle the password entry for login or registration."""
    try:
        user = update.effective_user
        entered_password = update.message.text
        phone_number = context.user_data.get('phone_number')
        
        # Delete message with password for security
        try:
            update.message.delete()
        except:
            logger.warning("Could not delete password message")
        
        if not phone_number:
            update.message.reply_text(
                "Что-то пошло не так. Пожалуйста, начните сначала с команды /start",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Check if this is a new user registration or login
        is_new_user = context.user_data.get('is_new_user', False)
        
        # Информируем пользователя о процессе
        processing_message = update.message.reply_text(
            "Обрабатываю ваш запрос...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        if is_new_user:
            # Register new user
            response = api_client.register_user(phone_number, entered_password)
            
            if 'error' in response:
                # Если при регистрации произошла ошибка
                if 'уже существует' in response.get('error', ''):
                    # Если пользователь существует, попробуем войти с введенным паролем
                    login_response = api_client.login_user(phone_number, entered_password)
                    
                    if 'error' not in login_response:
                        # Если вход удался, обрабатываем как успешный вход
                        response = login_response
                        # Уведомляем пользователя
                        processing_message.edit_text(
                            "Пользователь с таким номером уже существует. Пробую войти с указанным паролем..."
                        )
                    else:
                        # Если и вход не удался
                        processing_message.delete()
                        update.message.reply_text(
                            f"Пользователь с таким номером телефона уже существует, но указанный пароль неверный. "
                            f"Пожалуйста, введите правильный пароль или начните сначала с /start",
                            reply_markup=ReplyKeyboardRemove()
                        )
                        return PASSWORD
                else:
                    # Другие ошибки регистрации
                    processing_message.delete()
                    update.message.reply_text(
                        f"Ошибка при регистрации: {response['error']}. Пожалуйста, попробуйте снова или начните сначала с /start",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return PASSWORD
        else:
            # Login existing user
            response = api_client.login_user(phone_number, entered_password)
            
            if 'error' in response:
                # Если при входе произошла ошибка
                processing_message.delete()
                
                if 'Неверные учетные данные' in response.get('error', ''):
                    # Если неверный пароль
                    update.message.reply_text(
                        "Неверный пароль. Пожалуйста, попробуйте еще раз:",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return PASSWORD
                else:
                    # Другие ошибки входа
                    update.message.reply_text(
                        f"Ошибка при входе: {response['error']}. Пожалуйста, попробуйте снова или начните сначала с /start",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return PASSWORD
        
        # Если все прошло успешно, сохраняем данные пользователя
        processing_message.delete()
        
        # Save API user ID in local database
        UserRepository.update_user(
            user.id,
            api_user_id=response.get('id')
        )
        
        # Set hashed password for local authentication and store entered password in context
        UserRepository.set_password(user.id, entered_password)
        
        # Сохраняем пароль для API-запросов в контексте сессии
        context.user_data['api_password'] = entered_password
        
        # Clear user_data except for API password
        api_password = context.user_data.get('api_password')
        context.user_data.clear()
        context.user_data['api_password'] = api_password
        
        update.message.reply_text(
            "Спасибо! Вы успешно авторизованы.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in password handler: {e}")
        update.message.reply_text(
            f"Произошла ошибка при обработке пароля: {str(e)}. Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

def main_menu(update: Update, context: CallbackContext) -> int:
    """Handle main menu selection."""
    try:
        text = update.message.text
        user = update.effective_user
        
        if text == "📝 Создать метку настроения":
            update.message.reply_text(
                "Выберите эмодзи, который отражает ваше настроение:",
                reply_markup=get_emoji_keyboard()
            )
            return MOOD_EMOJI
        elif text == "👤 Профиль":
            return profile(update, context)
        elif text == "🔍 Настроение вокруг меня":
            update.message.reply_text(
                "Отправьте свою геолокацию, чтобы узнать настроение вокруг вас:",
                reply_markup=get_location_keyboard(user.id)
            )
            return AREA_MOOD
        elif text == "📊 Тренды":
            update.message.reply_text(
                "Отправьте свою геолокацию, чтобы узнать тренды настроений в вашем районе:",
                reply_markup=get_location_keyboard(user.id)
            )
            return TRENDS
        elif text == "🎭 События":
            update.message.reply_text(
                "Отправьте свою геолокацию, чтобы узнать о событиях в вашем районе:",
                reply_markup=get_location_keyboard(user.id)
            )
            return EVENTS
        else:
            update.message.reply_text(
                "Пожалуйста, выберите опцию из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in main_menu handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при обработке выбора меню. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def mood_emoji(update: Update, context: CallbackContext) -> int:
    """Handle emoji selection for mood."""
    try:
        text = update.message.text
        
        if text == "❌ Отмена":
            update.message.reply_text(
                "Создание метки настроения отменено.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        
        if text in EMOJI_OPTIONS:
            # Save selected emoji
            context.user_data['mood_emoji'] = text
            
            update.message.reply_text(
                "Отлично! Теперь добавьте комментарий к вашему настроению (или отправьте /skip, чтобы пропустить):",
                reply_markup=ReplyKeyboardRemove()
            )
            return MOOD_TEXT
        else:
            update.message.reply_text(
                "Пожалуйста, выберите эмодзи из предложенных вариантов:",
                reply_markup=get_emoji_keyboard()
            )
            return MOOD_EMOJI
    except Exception as e:
        logger.error(f"Error in mood_emoji handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при обработке выбора эмодзи. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=get_emoji_keyboard()
        )
        return MOOD_EMOJI

def skip_mood_text(update: Update, context: CallbackContext) -> int:
    """Skip adding text to mood."""
    try:
        user = update.effective_user
        context.user_data['mood_text'] = ""
        
        update.message.reply_text(
            "Отправьте свою геолокацию, чтобы привязать метку настроения к месту:",
            reply_markup=get_location_keyboard(user.id)
        )
        return MOOD_LOCATION
    except Exception as e:
        logger.error(f"Error in skip_mood_text handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при обработке команды /skip. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=get_location_keyboard(update.effective_user.id)
        )
        return MOOD_LOCATION

def mood_text(update: Update, context: CallbackContext) -> int:
    """Handle text for mood."""
    try:
        text = update.message.text
        user = update.effective_user
        
        if text == "/skip":
            return skip_mood_text(update, context)
        
        # Save mood text
        context.user_data['mood_text'] = text
        
        update.message.reply_text(
            "Отлично! Теперь отправьте свою геолокацию, чтобы привязать метку настроения к месту:",
            reply_markup=get_location_keyboard(user.id)
        )
        return MOOD_LOCATION
    except Exception as e:
        logger.error(f"Error in mood_text handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при обработке текста настроения. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=get_location_keyboard(update.effective_user.id)
        )
        return MOOD_LOCATION

def mood_location(update: Update, context: CallbackContext) -> int:
    """Store location and create a new mood."""
    try:
        user = update.effective_user
        emoji = context.user_data.get('mood_emoji', '😐')
        text = context.user_data.get('mood_text', '')
        
        # Используем обновленный метод для создания настроения
        if update.message.location:
            # Если пользователь отправил геолокацию
            latitude = update.message.location.latitude
            longitude = update.message.location.longitude
            
            # Обновляем местоположение пользователя и время последней метки
            UserRepository.update_mood_location_time(user.id, latitude, longitude)
            
            response = create_mood_with_api(user.id, emoji, latitude, longitude, text, context)
            
            if 'error' in response:
                update.message.reply_text(
                    f"Ошибка при создании настроения: {response['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.message.reply_text(
                    "Ваше настроение успешно записано! 👍",
                    reply_markup=get_main_menu_keyboard()
                )
                
            # Очищаем данные настроения
            context.user_data.pop('mood_emoji', None)
            context.user_data.pop('mood_text', None)
            
            return MAIN_MENU
        elif update.message.text == "🔄 Последняя геолокация":
            # Если пользователь выбрал использовать последнюю геолокацию
            location = UserRepository.get_user_location(user.id)
            
            if not location:
                update.message.reply_text(
                    "Не удалось найти вашу последнюю геолокацию. Пожалуйста, отправьте геолокацию.",
                    reply_markup=get_location_keyboard(user.id)
                )
                return MOOD_LOCATION
                
            latitude = location['latitude']
            longitude = location['longitude']
            
            # Обновляем только время последней метки, координаты оставляем те же
            UserRepository.update_mood_location_time(user.id)
            
            response = create_mood_with_api(user.id, emoji, latitude, longitude, text, context)
            
            if 'error' in response:
                update.message.reply_text(
                    f"Ошибка при создании настроения: {response['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.message.reply_text(
                    "Ваше настроение успешно записано с использованием последней метки! 👍",
                    reply_markup=get_main_menu_keyboard()
                )
                
            # Очищаем данные настроения
            context.user_data.pop('mood_emoji', None)
            context.user_data.pop('mood_text', None)
            
            return MAIN_MENU
        elif update.message.text == "❌ Отмена":
            update.message.reply_text(
                "Создание метки настроения отменено.",
                reply_markup=get_main_menu_keyboard()
            )
            # Очищаем данные настроения
            context.user_data.pop('mood_emoji', None)
            context.user_data.pop('mood_text', None)
            return MAIN_MENU
        else:
            update.message.reply_text(
                "Пожалуйста, отправьте свое местоположение, используя кнопку ниже.",
                reply_markup=get_location_keyboard(user.id)
            )
            return MOOD_LOCATION
    except Exception as e:
        logger.error(f"Error in mood_location handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при создании настроения. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def profile(update: Update, context: CallbackContext) -> int:
    """Show user profile and moods."""
    try:
        user = update.effective_user
        api_user_id, _ = get_user_api_credentials(user.id)
        
        # Получаем текущую страницу из контекста или устанавливаем 1 по умолчанию
        current_page = context.user_data.get('profile_page', 1)
        items_per_page = 5  # Количество меток на одной странице
        
        if not api_user_id:
            update.message.reply_text(
                "Ошибка: вы не авторизованы. Пожалуйста, начните с команды /start",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        
        # Получаем все настроения пользователя через API (без ограничения по времени)
        moods = get_api_data_with_auth(
            user.id, 
            api_client.get_user_moods,
            context,
            user_id=api_user_id
        )
        
        if isinstance(moods, dict) and 'error' in moods:
            update.message.reply_text(
                f"Ошибка при получении настроений: {moods['error']}",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        
        if not moods:
            update.message.reply_text(
                "У вас пока нет меток настроения. Создайте первую метку в главном меню!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        
        # Рассчитываем общее количество страниц
        total_pages = (len(moods) + items_per_page - 1) // items_per_page
        
        # Проверяем корректность текущей страницы
        if current_page < 1:
            current_page = 1
        elif current_page > total_pages:
            current_page = total_pages
            
        # Сохраняем текущую страницу в контексте
        context.user_data['profile_page'] = current_page
        
        # Вычисляем индексы для текущей страницы
        start_idx = (current_page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(moods))
        
        # Создаем сообщение с настроениями текущей страницы
        message = f"📊 <b>Ваши метки настроения (страница {current_page}/{total_pages}):</b>\n\n"
        
        for i, mood in enumerate(moods[start_idx:end_idx], start_idx + 1):
            emoji = mood['emoji']
            text = mood['text'] if mood['text'] else "[без комментария]"
            timestamp = datetime.fromisoformat(mood['timestamp'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%d.%m.%Y %H:%M")
            
            message += f"{i}. {emoji} {text}\n   {formatted_time}\n\n"
        
        # Добавляем кнопки для управления настроениями
        keyboard = []
        
        # Кнопки для удаления настроений на текущей странице
        for mood in moods[start_idx:end_idx]:
            mood_id = mood['id']
            emoji = mood['emoji']
            timestamp = datetime.fromisoformat(mood['timestamp'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%d.%m.%Y %H:%M")
            
            keyboard.append([
                InlineKeyboardButton(
                    f"Удалить {emoji} от {formatted_time}",
                    callback_data=f"delete_mood_{mood_id}"
                )
            ])
        
        # Кнопки навигации по страницам
        nav_buttons = []
        
        if current_page > 1:
            nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data="profile_prev"))
        
        if current_page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data="profile_next"))
            
        if nav_buttons:
            keyboard.append(nav_buttons)
            
        keyboard.append([InlineKeyboardButton("Назад в меню", callback_data="profile_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_html(
            message,
            reply_markup=reply_markup
        )
        
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in profile handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при загрузке профиля. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def profile_action(update: Update, context: CallbackContext) -> int:
    """Handle profile actions."""
    try:
        query = update.callback_query
        user = query.from_user
        
        if query.data == "profile_back":
            # Удаляем сообщение с профилем и возвращаемся в главное меню
            query.edit_message_text(
                text="Возврат в главное меню...",
            )
            query.message.reply_text(
                "Главное меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif query.data == "profile_prev":
            # Переход на предыдущую страницу
            current_page = context.user_data.get('profile_page', 1)
            context.user_data['profile_page'] = max(1, current_page - 1)
            
            # Получаем обновленный профиль
            return show_profile_page(update, context)
        elif query.data == "profile_next":
            # Переход на следующую страницу
            current_page = context.user_data.get('profile_page', 1)
            context.user_data['profile_page'] = current_page + 1
            
            # Получаем обновленный профиль
            return show_profile_page(update, context)
        else:
            return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in profile_action handler: {e}")
        query.edit_message_text(
            text="Произошла ошибка при обработке действия профиля. Пожалуйста, попробуйте позже."
        )
        return MAIN_MENU

def delete_mood_callback(update: Update, context: CallbackContext) -> int:
    """Handle deletion of a mood."""
    try:
        query = update.callback_query
        query.answer()
        
        # Получаем ID настроения из callback data
        mood_id = int(query.data.split('_')[2])
        user = query.from_user
        
        # Удаляем настроение через API
        success = delete_mood_with_api(user.id, mood_id, context)
        
        if success:
            # Вместо простого сообщения об удалении, обновляем профиль
            return show_profile_page(update, context)
        else:
            query.edit_message_text(
                text="Не удалось удалить настроение. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Вернуться к профилю", callback_data="profile_back")
                ]])
            )
        
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in delete_mood_callback handler: {e}")
        query.edit_message_text(
            text="Произошла ошибка при удалении настроения.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Вернуться к профилю", callback_data="profile_back")
            ]])
        )
        return MAIN_MENU

def area_mood(update: Update, context: CallbackContext) -> int:
    """Show mood in the area around the user."""
    try:
        user = update.effective_user
        
        if update.message.location:
            latitude = update.message.location.latitude
            longitude = update.message.location.longitude
            
            # Обновляем местоположение пользователя для отслеживания событий
            UserRepository.update_mood_location_time(user.id, latitude, longitude)
            
            # Получаем настроение области через API
            area_mood_data = get_api_data_with_auth(
                user.id,
                api_client.get_area_mood,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(area_mood_data, dict) and 'error' in area_mood_data:
                update.message.reply_text(
                    f"Ошибка при получении настроения области: {area_mood_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о настроении области
            if area_mood_data:
                message = f"🗺 <b>Настроение вокруг вас</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += f" <b>(радиус 5 км):</b>\n\n"
                
                # Используем правильные ключи из ответа API
                if 'dominant_emoji' in area_mood_data:
                    message += f"Преобладающее настроение: {area_mood_data['dominant_emoji']}\n"
                
                if 'moods_count' in area_mood_data:
                    message += f"Всего меток настроения: {area_mood_data['moods_count']}\n"
                
                if 'mood_counts' in area_mood_data:
                    message += "\n<b>Распределение настроений:</b>\n"
                    total_moods = area_mood_data['moods_count']
                    for emoji, count in area_mood_data['mood_counts'].items():
                        percentage = count / total_moods * 100
                        message += f"{emoji}: {count} ({percentage:.1f}%)\n"
                
                if 'mood_percentage' in area_mood_data:
                    message += f"\nПроцент положительных настроений: {area_mood_data['mood_percentage']}%\n"
            else:
                message = "В этой области пока нет меток настроения."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "🔄 Последняя геолокация":
            # Если пользователь выбрал использовать последнюю геолокацию
            location = UserRepository.get_user_location(user.id)
            
            if not location:
                update.message.reply_text(
                    "Не удалось найти вашу последнюю геолокацию. Пожалуйста, отправьте геолокацию.",
                    reply_markup=get_location_keyboard(user.id)
                )
                return AREA_MOOD
                
            latitude = location['latitude']
            longitude = location['longitude']
            
            # Обновляем время последней метки, координаты оставляем те же
            UserRepository.update_mood_location_time(user.id)
            
            # Получаем настроение области через API
            area_mood_data = get_api_data_with_auth(
                user.id,
                api_client.get_area_mood,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(area_mood_data, dict) and 'error' in area_mood_data:
                update.message.reply_text(
                    f"Ошибка при получении настроения области: {area_mood_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о настроении области
            if area_mood_data:
                message = f"🗺 <b>Настроение вокруг последней метки</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += f" <b>(радиус 5 км):</b>\n\n"
                
                # Используем правильные ключи из ответа API
                if 'dominant_emoji' in area_mood_data:
                    message += f"Преобладающее настроение: {area_mood_data['dominant_emoji']}\n"
                
                if 'moods_count' in area_mood_data:
                    message += f"Всего меток настроения: {area_mood_data['moods_count']}\n"
                
                if 'mood_counts' in area_mood_data:
                    message += "\n<b>Распределение настроений:</b>\n"
                    total_moods = area_mood_data['moods_count']
                    for emoji, count in area_mood_data['mood_counts'].items():
                        percentage = count / total_moods * 100
                        message += f"{emoji}: {count} ({percentage:.1f}%)\n"
                
                if 'mood_percentage' in area_mood_data:
                    message += f"\nПроцент положительных настроений: {area_mood_data['mood_percentage']}%\n"
            else:
                message = "В этой области пока нет меток настроения."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "❌ Отмена":
            update.message.reply_text(
                "Операция отменена.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        else:
            update.message.reply_text(
                "Пожалуйста, отправьте своё местоположение, чтобы узнать преобладающее настроение в вашем районе.",
                reply_markup=get_location_keyboard(user.id)
            )
            return AREA_MOOD
    except Exception as e:
        logger.error(f"Error in area_mood handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при анализе настроения области. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def trends(update: Update, context: CallbackContext) -> int:
    """Show mood trends."""
    try:
        user = update.effective_user
        
        if update.message.location:
            latitude = update.message.location.latitude
            longitude = update.message.location.longitude
            
            # Обновляем местоположение пользователя для отслеживания событий
            UserRepository.update_mood_location_time(user.id, latitude, longitude)
            
            # Получаем тренды настроения через API
            trends_data = get_api_data_with_auth(
                user.id,
                api_client.get_trends,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(trends_data, dict) and 'error' in trends_data:
                update.message.reply_text(
                    f"Ошибка при получении трендов: {trends_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о трендах
            if trends_data:
                message = f"📊 <b>Тренды настроений за последние 24 часа</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += ":\n\n"
                
                if 'trend_direction' in trends_data:
                    trend_direction = trends_data['trend_direction']
                    trend_text = "стабильное" if trend_direction == 'stable' else ("улучшается" if trend_direction == 'up' else "ухудшается")
                    message += f"Общий тренд: настроение {trend_text}\n\n"
                
                if 'emoji_counts' in trends_data:
                    message += "<b>Популярные настроения:</b>\n"
                    total_count = sum(trends_data['emoji_counts'].values())
                    
                    # Сортируем эмодзи по количеству (от большего к меньшему)
                    sorted_emojis = sorted(
                        trends_data['emoji_counts'].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                    
                    for emoji, count in sorted_emojis:
                        if total_count > 0:
                            percentage = (count / total_count) * 100
                            message += f"{emoji}: {count} ({percentage:.1f}%)\n"
                    
                    message += f"\nВсего меток настроения: {total_count}"
                
                # Добавляем информацию о временных периодах, если она есть
                if 'time_periods' in trends_data and 'mood_percentages' in trends_data:
                    message += "\n\n<b>Изменение настроения по времени:</b>\n"
                    periods = trends_data['time_periods']
                    percentages = trends_data['mood_percentages']
                    
                    for i in range(min(len(periods), len(percentages))):
                        message += f"{periods[i]}: {percentages[i]}%\n"
            else:
                message = "Недостаточно данных для анализа трендов настроения."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "🔄 Последняя геолокация":
            # Если пользователь выбрал использовать последнюю геолокацию
            location = UserRepository.get_user_location(user.id)
            
            if not location:
                update.message.reply_text(
                    "Не удалось найти вашу последнюю геолокацию. Пожалуйста, отправьте геолокацию.",
                    reply_markup=get_location_keyboard(user.id)
                )
                return TRENDS
                
            latitude = location['latitude']
            longitude = location['longitude']
            
            # Обновляем время последней метки, координаты оставляем те же
            UserRepository.update_mood_location_time(user.id)
            
            # Получаем тренды настроения через API
            trends_data = get_api_data_with_auth(
                user.id,
                api_client.get_trends,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(trends_data, dict) and 'error' in trends_data:
                update.message.reply_text(
                    f"Ошибка при получении трендов: {trends_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о трендах
            if trends_data:
                message = f"📊 <b>Тренды настроений за последние 24 часа (последняя метка)</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += ":\n\n"
                
                if 'trend_direction' in trends_data:
                    trend_direction = trends_data['trend_direction']
                    trend_text = "стабильное" if trend_direction == 'stable' else ("улучшается" if trend_direction == 'up' else "ухудшается")
                    message += f"Общий тренд: настроение {trend_text}\n\n"
                
                if 'emoji_counts' in trends_data:
                    message += "<b>Популярные настроения:</b>\n"
                    total_count = sum(trends_data['emoji_counts'].values())
                    
                    # Сортируем эмодзи по количеству (от большего к меньшему)
                    sorted_emojis = sorted(
                        trends_data['emoji_counts'].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                    
                    for emoji, count in sorted_emojis:
                        if total_count > 0:
                            percentage = (count / total_count) * 100
                            message += f"{emoji}: {count} ({percentage:.1f}%)\n"
                    
                    message += f"\nВсего меток настроения: {total_count}"
                
                # Добавляем информацию о временных периодах, если она есть
                if 'time_periods' in trends_data and 'mood_percentages' in trends_data:
                    message += "\n\n<b>Изменение настроения по времени:</b>\n"
                    periods = trends_data['time_periods']
                    percentages = trends_data['mood_percentages']
                    
                    for i in range(min(len(periods), len(percentages))):
                        message += f"{periods[i]}: {percentages[i]}%\n"
            else:
                message = "Недостаточно данных для анализа трендов настроения."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "❌ Отмена":
            update.message.reply_text(
                "Операция отменена.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        else:
            update.message.reply_text(
                "Пожалуйста, отправьте своё местоположение, чтобы узнать тренды настроений в вашем районе:",
                reply_markup=get_location_keyboard(user.id)
            )
            return TRENDS
    except Exception as e:
        logger.error(f"Error in trends handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при анализе трендов настроения. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def events(update: Update, context: CallbackContext) -> int:
    """Show mood-based events."""
    try:
        user = update.effective_user
        
        if update.message.location:
            latitude = update.message.location.latitude
            longitude = update.message.location.longitude
            
            # Обновляем местоположение пользователя для отслеживания событий
            UserRepository.update_mood_location_time(user.id, latitude, longitude)
            
            # Получаем события через API
            events_data = get_api_data_with_auth(
                user.id,
                api_client.get_events,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(events_data, dict) and 'error' in events_data:
                update.message.reply_text(
                    f"Ошибка при получении событий: {events_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о событиях
            if events_data and isinstance(events_data, list) and len(events_data) > 0:
                message = f"🎭 <b>События за последние 24 часа</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += ":\n\n"
                
                for i, event in enumerate(events_data[:5], 1):  # Показываем только 5 важнейших событий
                    title = event.get('type', 'Неизвестное событие')
                    description = event.get('description', '')
                    if not description and 'keywords' in event:
                        description = f"Ключевые слова: {', '.join(event['keywords'])}"
                    confidence = event.get('confidence', 0)
                    emoji = event.get('dominant_emoji', '')
                    
                    message += f"{i}. <b>{title}</b> {emoji}\n"
                    if description:
                        message += f"{description}\n"
                    message += f"Достоверность: {confidence}%\n\n"
                    
                if len(events_data) > 5:
                    message += f"...и еще {len(events_data) - 5} событий"
            else:
                message = "За последние 24 часа не обнаружено значимых событий."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "🔄 Последняя геолокация":
            # Если пользователь выбрал использовать последнюю геолокацию
            location = UserRepository.get_user_location(user.id)
            
            if not location:
                update.message.reply_text(
                    "Не удалось найти вашу последнюю геолокацию. Пожалуйста, отправьте геолокацию.",
                    reply_markup=get_location_keyboard(user.id)
                )
                return EVENTS
                
            latitude = location['latitude']
            longitude = location['longitude']
            
            # Получаем события через API
            events_data = get_api_data_with_auth(
                user.id,
                api_client.get_events,
                context,
                latitude=latitude,
                longitude=longitude,
                radius=5.0,  # По умолчанию радиус 5 км
                hours=24  # За последние 24 часа
            )
            
            if isinstance(events_data, dict) and 'error' in events_data:
                update.message.reply_text(
                    f"Ошибка при получении событий: {events_data['error']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return MAIN_MENU
            
            # Получаем адрес по координатам
            address = get_address_from_coordinates(latitude, longitude)
            
            # Формируем сообщение о событиях
            if events_data and isinstance(events_data, list) and len(events_data) > 0:
                message = f"🎭 <b>События за последние 24 часа (последняя метка)</b>"
                if address:
                    message += f" <b>рядом с</b> {address}"
                message += ":\n\n"
                
                for i, event in enumerate(events_data[:5], 1):  # Показываем только 5 важнейших событий
                    title = event.get('type', 'Неизвестное событие')
                    description = event.get('description', '')
                    if not description and 'keywords' in event:
                        description = f"Ключевые слова: {', '.join(event['keywords'])}"
                    confidence = event.get('confidence', 0)
                    emoji = event.get('dominant_emoji', '')
                    
                    message += f"{i}. <b>{title}</b> {emoji}\n"
                    if description:
                        message += f"{description}\n"
                    message += f"Достоверность: {confidence}%\n\n"
                    
                if len(events_data) > 5:
                    message += f"...и еще {len(events_data) - 5} событий"
            else:
                message = "За последние 24 часа не обнаружено значимых событий."
            
            update.message.reply_html(
                message,
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        elif update.message.text == "❌ Отмена":
            update.message.reply_text(
                "Операция отменена.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        else:
            update.message.reply_text(
                "Пожалуйста, отправьте своё местоположение, чтобы узнать о событиях в вашем районе:",
                reply_markup=get_location_keyboard(user.id)
            )
            return EVENTS
    except Exception as e:
        logger.error(f"Error in events handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при получении событий. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel and end the conversation."""
    try:
        update.message.reply_text(
            "Действие отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in cancel handler: {e}")
        update.message.reply_text(
            "Произошла ошибка при отмене действия. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

def error_handler(update: Update, context: CallbackContext):
    """Log errors caused by updates."""
    try:
        # Log the error
        logger.error(f"Update {update} caused error {context.error}")
        
        # Log traceback info
        import traceback
        traceback.print_exc()
        
        # Send message to the user if possible
        if update and update.effective_message:
            update.effective_message.reply_text(
                "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже или свяжитесь с администратором.",
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def show_profile_page(update: Update, context: CallbackContext) -> int:
    """Show a specific page of user profile with moods."""
    try:
        query = update.callback_query
        user = query.from_user
        api_user_id, _ = get_user_api_credentials(user.id)
        
        # Получаем текущую страницу из контекста
        current_page = context.user_data.get('profile_page', 1)
        items_per_page = 5  # Количество меток на одной странице
        
        if not api_user_id:
            query.edit_message_text(
                text="Ошибка: вы не авторизованы. Пожалуйста, начните с команды /start"
            )
            return MAIN_MENU
        
        # Получаем все настроения пользователя через API
        moods = get_api_data_with_auth(
            user.id, 
            api_client.get_user_moods,
            context,
            user_id=api_user_id
        )
        
        if isinstance(moods, dict) and 'error' in moods:
            query.edit_message_text(
                text=f"Ошибка при получении настроений: {moods['error']}"
            )
            return MAIN_MENU
        
        if not moods:
            query.edit_message_text(
                text="У вас пока нет меток настроения. Создайте первую метку в главном меню!"
            )
            return MAIN_MENU
        
        # Рассчитываем общее количество страниц
        total_pages = (len(moods) + items_per_page - 1) // items_per_page
        
        # Проверяем корректность текущей страницы
        if current_page < 1:
            current_page = 1
        elif current_page > total_pages:
            current_page = total_pages
            
        # Сохраняем текущую страницу в контексте
        context.user_data['profile_page'] = current_page
        
        # Вычисляем индексы для текущей страницы
        start_idx = (current_page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(moods))
        
        # Создаем сообщение с настроениями текущей страницы
        message = f"📊 <b>Ваши метки настроения (страница {current_page}/{total_pages}):</b>\n\n"
        
        for i, mood in enumerate(moods[start_idx:end_idx], start_idx + 1):
            emoji = mood['emoji']
            text = mood['text'] if mood['text'] else "[без комментария]"
            timestamp = datetime.fromisoformat(mood['timestamp'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%d.%m.%Y %H:%M")
            
            message += f"{i}. {emoji} {text}\n   {formatted_time}\n\n"
        
        # Добавляем кнопки для управления настроениями
        keyboard = []
        
        # Кнопки для удаления настроений на текущей странице
        for mood in moods[start_idx:end_idx]:
            mood_id = mood['id']
            emoji = mood['emoji']
            timestamp = datetime.fromisoformat(mood['timestamp'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%d.%m.%Y %H:%M")
            
            keyboard.append([
                InlineKeyboardButton(
                    f"Удалить {emoji} от {formatted_time}",
                    callback_data=f"delete_mood_{mood_id}"
                )
            ])
        
        # Кнопки навигации по страницам
        nav_buttons = []
        
        if current_page > 1:
            nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data="profile_prev"))
        
        if current_page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data="profile_next"))
            
        if nav_buttons:
            keyboard.append(nav_buttons)
            
        keyboard.append([InlineKeyboardButton("Назад в меню", callback_data="profile_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем существующее сообщение
        query.edit_message_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in show_profile_page handler: {e}")
        try:
            query.edit_message_text(
                text="Произошла ошибка при загрузке профиля. Пожалуйста, попробуйте позже."
            )
        except:
            pass
        return MAIN_MENU

def main():
    """
    Основная функция запуска бота.
    
    Эта функция создает экземпляр бота, настраивает обработчики команд и сообщений,
    и запускает бота в режиме long polling (постоянного опроса сервера Telegram).
    """
    try:
        # Создаем объект Updater и передаем ему токен бота
        # Updater - это основной класс, который автоматически получает обновления от Telegram
        updater = Updater(TOKEN)
        
        # Получаем диспетчер для регистрации обработчиков
        # Диспетчер управляет обработчиками и вызывает их при получении соответствующих сообщений
        dp = updater.dispatcher
        
        # Добавляем обработчик разговора (ConversationHandler)
        # ConversationHandler управляет диалогом с пользователем, переключаясь между состояниями
        conv_handler = ConversationHandler(
            # Точки входа - команды, которые могут начать диалог
            entry_points=[CommandHandler('start', start)],
            
            # Состояния диалога и соответствующие им обработчики
            states={
                START: [MessageHandler(Filters.text, start)],
                PHONE_NUMBER: [MessageHandler(Filters.contact | Filters.text, phone_number)],
                PASSWORD: [MessageHandler(Filters.text, password)],
                MAIN_MENU: [MessageHandler(Filters.text, main_menu)],
                MOOD_EMOJI: [MessageHandler(Filters.text, mood_emoji)],
                MOOD_TEXT: [
                    MessageHandler(Filters.text & ~Filters.regex('^(❌ Отмена|⏩ Пропустить)$'), mood_text),
                    MessageHandler(Filters.regex('^⏩ Пропустить$'), skip_mood_text)
                ],
                MOOD_LOCATION: [
                    MessageHandler(Filters.location, mood_location),
                    MessageHandler(Filters.regex('^🔄 Использовать последнюю геолокацию$'), mood_location),
                    MessageHandler(Filters.regex('^❌ Отмена$'), cancel)
                ],
                PROFILE: [MessageHandler(Filters.text, profile)],
                VIEW_MOODS: [MessageHandler(Filters.text, profile)],
                DELETE_MOOD: [MessageHandler(Filters.text, profile)],
                AREA_MOOD: [
                    MessageHandler(Filters.location, area_mood),
                    MessageHandler(Filters.regex('^🔄 Использовать последнюю геолокацию$'), area_mood),
                    MessageHandler(Filters.regex('^❌ Отмена$'), area_mood),
                    MessageHandler(Filters.text, area_mood)
                ],
                AREA_RADIUS: [MessageHandler(Filters.text, area_mood)],
                AREA_HOURS: [MessageHandler(Filters.text, area_mood)],
                TRENDS: [
                    MessageHandler(Filters.location, trends),
                    MessageHandler(Filters.regex('^🔄 Использовать последнюю геолокацию$'), trends),
                    MessageHandler(Filters.regex('^❌ Отмена$'), trends),
                    MessageHandler(Filters.text, trends)
                ],
                EVENTS: [
                    MessageHandler(Filters.location, events),
                    MessageHandler(Filters.regex('^🔄 Использовать последнюю геолокацию$'), events),
                    MessageHandler(Filters.regex('^❌ Отмена$'), events),
                    MessageHandler(Filters.text, events)
                ]
            },
            # Точки выхода - обработчики, которые завершают диалог
            fallbacks=[CommandHandler('cancel', cancel)],
            name="main_conversation",
            persistent=False  # Диалог не сохраняется между перезапусками бота
        )
        
        # Регистрируем обработчик диалога в диспетчере
        dp.add_handler(conv_handler)
        
        # Добавляем обработчики для inline-кнопок (кнопок, встроенных в сообщения)
        dp.add_handler(CallbackQueryHandler(delete_mood_callback, pattern='^delete_mood_'))
        dp.add_handler(CallbackQueryHandler(profile_action, pattern='^profile_'))
        
        # Регистрируем обработчик ошибок
        dp.add_error_handler(error_handler)
        
        # Запускаем бота
        # start_polling() запускает бота в режиме long polling - 
        # постоянного опроса серверов Telegram на наличие новых сообщений
        updater.start_polling()
        logger.info("Бот запущен и готов к работе")
        
        # Запускаем бота до нажатия Ctrl-C или получения сигнала остановки
        # idle() блокирует выполнение программы до получения сигнала остановки
        updater.idle()
        
    except Exception as e:
        logger.error(f"Ошибка в функции main: {e}")

if __name__ == '__main__':
    main() 