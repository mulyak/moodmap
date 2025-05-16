import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from werkzeug.security import generate_password_hash, check_password_hash

# Настраиваем логгер
logger = logging.getLogger(__name__)

# Инициализируем базовый класс и движок SQLAlchemy
Base = declarative_base()

# Создаем движок базы данных
db_path = os.path.abspath("telegram_bot.db")
engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

# Создаем фабрику сессий с областью видимости - потокобезопасную без явной многопоточности
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

class User(Base):
    """
    Модель пользователя Telegram-бота.
    Хранит информацию о пользователях и их учетные данные для API.
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    phone_number = Column(String, unique=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    api_user_id = Column(Integer)
    password_hash = Column(String)
    created_at = Column(DateTime, default=func.current_timestamp())
    
    # Отношение один-к-одному с моделью UserLocation
    location = relationship("UserLocation", uselist=False, back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password):
        """
        Устанавливает хешированный пароль для пользователя.
        
        Аргументы:
            password - пароль пользователя
        """
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """
        Проверяет правильность пароля пользователя.
        
        Аргументы:
            password - пароль для проверки
            
        Возвращает:
            True, если пароль верный, иначе False
        """
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class UserLocation(Base):
    """
    Модель местоположения пользователя.
    Хранит информацию о последней известной геолокации пользователя.
    """
    __tablename__ = 'user_locations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, ForeignKey('users.telegram_id', ondelete='CASCADE'), unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    last_notification_time = Column(DateTime)
    last_mood_location_time = Column(DateTime)  # Время последней метки настроения
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Обратное отношение к модели User
    user = relationship("User", back_populates="location")

# Создаем таблицы в базе данных, если они не существуют
Base.metadata.create_all(engine)

class UserRepository:
    """
    Репозиторий для работы с пользователями в базе данных.
    Предоставляет методы для создания, обновления и получения информации о пользователях.
    """
    @staticmethod
    def create_user(telegram_id, phone_number=None, username=None, first_name=None, last_name=None, api_user_id=None, password=None):
        """
        Создание нового пользователя в базе данных.
        
        Аргументы:
            telegram_id - уникальный идентификатор пользователя в Telegram
            phone_number - номер телефона пользователя (необязательно)
            username - имя пользователя в Telegram (необязательно)
            first_name - имя пользователя (необязательно)
            last_name - фамилия пользователя (необязательно)
            api_user_id - ID пользователя в API (необязательно)
            password - пароль пользователя (необязательно)
            
        Возвращает:
            Объект пользователя
        """
        session = Session()
        try:
            # Проверяем, существует ли пользователь
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if user:
                # Если пользователь существует, возвращаем его
                return user
            
            # Создаем нового пользователя
            user = User(
                telegram_id=telegram_id,
                phone_number=phone_number,
                username=username,
                first_name=first_name,
                last_name=last_name,
                api_user_id=api_user_id
            )
            
            # Устанавливаем пароль, если он указан
            if password:
                user.set_password(password)
                
            session.add(user)
            session.commit()
            return user
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating user: {e}")
            return None
        finally:
            session.close()
    
    @staticmethod
    def update_user(telegram_id, **kwargs):
        """
        Обновление данных пользователя в базе данных.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            **kwargs - пары ключ-значение с полями для обновления
            
        Возвращает:
            True, если обновление выполнено успешно, иначе False
        """
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                return False
                
            # Обрабатываем специальный случай для пароля
            if 'password' in kwargs:
                user.set_password(kwargs.pop('password'))
            
            # Обновляем остальные атрибуты
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
                    
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating user: {e}")
            return False
        finally:
            session.close()
    
    @staticmethod
    def set_password(telegram_id, password):
        """
        Устанавливает хешированный пароль для пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            password - пароль пользователя
            
        Возвращает:
            True, если обновление выполнено успешно, иначе False
        """
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                return False
                
            user.set_password(password)
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error setting password: {e}")
            return False
        finally:
            session.close()
    
    @staticmethod
    def check_password(telegram_id, password):
        """
        Проверяет правильность пароля пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            password - пароль для проверки
            
        Возвращает:
            True, если пароль верный, иначе False
        """
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                return False
                
            return user.check_password(password)
            
        except Exception as e:
            logger.error(f"Error checking password: {e}")
            return False
        finally:
            session.close()
    
    @staticmethod
    def get_user_by_telegram_id(telegram_id):
        """
        Получение информации о пользователе по его Telegram ID.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            
        Возвращает:
            Словарь с данными пользователя или None, если пользователь не найден
        """
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                return None
                
            # Преобразуем объект пользователя в словарь
            user_dict = {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'phone_number': user.phone_number,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'api_user_id': user.api_user_id,
                'password_hash': user.password_hash,
                'created_at': user.created_at
            }
            
            return user_dict
            
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
        finally:
            session.close()
    
    @staticmethod
    def get_user_by_phone(phone_number):
        """
        Получение информации о пользователе по его номеру телефона.
        
        Аргументы:
            phone_number - номер телефона пользователя
            
        Возвращает:
            Словарь с данными пользователя или None, если пользователь не найден
        """
        session = Session()
        try:
            user = session.query(User).filter_by(phone_number=phone_number).first()
            
            if not user:
                return None
                
            # Преобразуем объект пользователя в словарь
            user_dict = {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'phone_number': user.phone_number,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'api_user_id': user.api_user_id,
                'password_hash': user.password_hash,
                'created_at': user.created_at
            }
            
            return user_dict
            
        except Exception as e:
            logger.error(f"Error getting user by phone: {e}")
            return None
        finally:
            session.close()
            
    @staticmethod
    def update_user_location(telegram_id, latitude, longitude):
        """
        Обновляет или создает запись о местоположении пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            latitude - широта
            longitude - долгота
            
        Возвращает:
            True, если операция выполнена успешно, иначе False
        """
        session = Session()
        try:
            # Проверяем существование пользователя
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                logger.error(f"User with telegram_id {telegram_id} not found")
                return False
                
            # Проверяем существование записи о местоположении
            location = session.query(UserLocation).filter_by(telegram_id=telegram_id).first()
            
            if location:
                # Обновляем существующую запись
                location.latitude = latitude
                location.longitude = longitude
                location.updated_at = func.current_timestamp()
            else:
                # Создаем новую запись
                location = UserLocation(
                    telegram_id=telegram_id,
                    latitude=latitude,
                    longitude=longitude
                )
                session.add(location)
                
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating user location: {e}")
            return False
        finally:
            session.close()
            
    @staticmethod
    def update_mood_location_time(telegram_id, latitude=None, longitude=None):
        """
        Обновляет время последней метки настроения пользователя и опционально местоположение.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            latitude - широта (необязательно)
            longitude - долгота (необязательно)
            
        Возвращает:
            True, если обновление выполнено успешно, иначе False
        """
        session = Session()
        try:
            # Проверяем существование записи о местоположении
            location = session.query(UserLocation).filter_by(telegram_id=telegram_id).first()
            
            if not location:
                # Если записи нет и не указаны координаты, не можем создать запись
                if latitude is None or longitude is None:
                    return False
                    
                # Создаем новую запись с указанными координатами
                location = UserLocation(
                    telegram_id=telegram_id,
                    latitude=latitude,
                    longitude=longitude,
                    last_mood_location_time=datetime.now()
                )
                session.add(location)
            else:
                # Обновляем время последней метки настроения
                location.last_mood_location_time = datetime.now()
                
                # Если указаны координаты, обновляем и их
                if latitude is not None and longitude is not None:
                    location.latitude = latitude
                    location.longitude = longitude
                    
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating mood location time: {e}")
            return False
        finally:
            session.close()
            
    @staticmethod
    def get_user_location(telegram_id):
        """
        Получает последнее сохраненное местоположение пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            
        Возвращает:
            Словарь с данными о местоположении или None, если местоположение не найдено
        """
        session = Session()
        try:
            location = session.query(UserLocation).filter_by(telegram_id=telegram_id).first()
            
            if not location:
                return None
                
            # Преобразуем объект местоположения в словарь
            location_dict = {
                'id': location.id,
                'telegram_id': location.telegram_id,
                'latitude': location.latitude,
                'longitude': location.longitude,
                'last_notification_time': location.last_notification_time,
                'last_mood_location_time': location.last_mood_location_time,
                'updated_at': location.updated_at
            }
            
            return location_dict
            
        except Exception as e:
            logger.error(f"Error getting user location: {e}")
            return None
        finally:
            session.close()
            
    @staticmethod
    def update_notification_time(telegram_id):
        """
        Обновляет время последнего уведомления пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            
        Возвращает:
            True, если обновление выполнено успешно, иначе False
        """
        session = Session()
        try:
            location = session.query(UserLocation).filter_by(telegram_id=telegram_id).first()
            
            if not location:
                return False
                
            location.last_notification_time = datetime.now()
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating notification time: {e}")
            return False
        finally:
            session.close()
            
    @staticmethod
    def get_users_with_locations():
        """
        Получает список всех пользователей с сохраненными местоположениями.
        
        Возвращает:
            Список словарей с данными пользователей и их местоположениями
        """
        session = Session()
        try:
            # Объединяем таблицы User и UserLocation
            query = session.query(
                User.telegram_id,
                User.api_user_id,
                UserLocation.latitude,
                UserLocation.longitude,
                UserLocation.last_notification_time
            ).join(UserLocation, User.telegram_id == UserLocation.telegram_id)
            
            # Фильтруем только пользователей с API ID
            query = query.filter(User.api_user_id != None)
            
            # Выполняем запрос и получаем результаты
            results = query.all()
            
            # Преобразуем результаты в список словарей
            users_with_locations = []
            for row in results:
                user_data = {
                    'telegram_id': row[0],
                    'api_user_id': row[1],
                    'latitude': row[2],
                    'longitude': row[3],
                    'last_notification_time': row[4]
                }
                users_with_locations.append(user_data)
                
            return users_with_locations
            
        except Exception as e:
            logger.error(f"Error getting users with locations: {e}")
            return []
        finally:
            session.close()
            
    @staticmethod
    def is_last_location_valid(telegram_id, max_minutes=5):
        """
        Проверяет, актуальна ли последняя метка местоположения пользователя.
        
        Аргументы:
            telegram_id - ID пользователя в Telegram
            max_minutes - максимальное время в минутах, в течение которого метка считается актуальной
            
        Возвращает:
            True, если последняя метка актуальна (в пределах указанного времени), иначе False
        """
        session = Session()
        try:
            location = session.query(UserLocation).filter_by(telegram_id=telegram_id).first()
            
            if not location or not location.last_mood_location_time:
                return False
                
            # Проверяем, прошло ли не более max_minutes с момента последней метки
            time_diff = datetime.now() - location.last_mood_location_time
            return time_diff.total_seconds() <= max_minutes * 60
            
        except Exception as e:
            logger.error(f"Error checking last location validity: {e}")
            return False
        finally:
            session.close() 