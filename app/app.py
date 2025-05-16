from flask import Flask, render_template, redirect, url_for, request, jsonify, session, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import secrets
from datetime import datetime, timedelta
from mood_analyzer import MoodAnalyzer

# Функция для нормализации телефонных номеров
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

# Инициализация приложения Flask
app = Flask(__name__)
# Настройки приложения:
# SECRET_KEY - секретный ключ для безопасности (нужен для работы с формами и сессиями)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
# SQLALCHEMY_DATABASE_URI - путь к базе данных (в этом случае используется SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///moodmap.db'
# Отключение отслеживания изменений в SQLAlchemy для экономии ресурсов
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Поддержка русских символов в JSON-ответах
app.config['JSON_AS_ASCII'] = False

# Инициализация дополнительных модулей
db = SQLAlchemy(app)
# LoginManager - управляет пользовательскими сессиями (вход/выход)
login_manager = LoginManager(app)
# Указываем, куда перенаправлять пользователя при попытке доступа к защищенным страницам
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'

# Определение моделей (таблиц) базы данных
# Модель User - хранит данные о пользователях
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Уникальный идентификатор пользователя
    phone_number = db.Column(db.String(20), unique=True, nullable=False)  # Номер телефона (должен быть уникальным)
    password_hash = db.Column(db.String(128))  # Хеш пароля (не сам пароль, для безопасности)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Дата регистрации
    moods = db.relationship('Mood', backref='author', lazy='dynamic')  # Связь с моделью Mood (один ко многим)
    
    # Метод для установки пароля (хеширование для безопасности)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    # Метод для проверки пароля
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Модель Mood - хранит данные о настроениях пользователей
class Mood(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Уникальный идентификатор записи настроения
    emoji = db.Column(db.String(10), nullable=False)  # Эмодзи, отражающее настроение
    text = db.Column(db.String(280))  # Текстовое описание настроения (необязательно)
    latitude = db.Column(db.Float, nullable=False)  # Широта местоположения
    longitude = db.Column(db.Float, nullable=False)  # Долгота местоположения
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # Время создания записи
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Связь с пользователем, создавшим запись

# Функция для загрузки пользователя по ID (нужна для работы с сессиями)
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Вспомогательные функции
# Функция для получения данных о настроениях из базы с возможностью фильтрации
def get_mood_data_for_api(lat=None, lng=None, radius=None, hours=None, emojis=None):
    """Получение данных о настроениях из базы с фильтрацией по разным параметрам
    
    Аргументы:
        lat (float, необязательно): Широта для фильтрации по местоположению
        lng (float, необязательно): Долгота для фильтрации по местоположению
        radius (float, необязательно): Радиус в км для фильтрации по местоположению
        hours (float, необязательно): Часы для фильтрации по времени (поддерживает дробные значения)
        emojis (список, необязательно): Список эмодзи для фильтрации
    """
    # Получаем все настроения из базы данных
    moods = Mood.query.all()
    # Преобразуем данные из базы в формат для API
    result = [{
        'id': mood.id,
        'emoji': mood.emoji,
        'text': mood.text or '',
        'latitude': mood.latitude,
        'longitude': mood.longitude,
        'timestamp': mood.timestamp.isoformat(),
        'user_id': mood.user_id
    } for mood in moods]
    
    # Применяем фильтр по времени, если указан
    if hours is not None:
        # Поддержка дробных значений часов для минутных фильтров
        cutoff_time = datetime.utcnow() - timedelta(hours=float(hours))
        result = [mood for mood in result if datetime.fromisoformat(mood['timestamp']) > cutoff_time]
    
    # Применяем фильтр по эмодзи, если указан
    if emojis and len(emojis) > 0:
        result = [mood for mood in result if mood['emoji'] in emojis]
    
    # Применяем фильтр по местоположению, если указан
    if lat is not None and lng is not None and radius is not None:
        analyzer = MoodAnalyzer([])  # Создаем экземпляр только для использования функции расчета расстояния
        result = [
            mood for mood in result 
            if analyzer._calculate_distance(lat, lng, mood['latitude'], mood['longitude']) <= radius
        ]
    
    return result

# API-конечные точки для аутентификации и управления пользователями
# Регистрация нового пользователя через API
@app.route('/api/auth/register', methods=['POST'])
def api_register():
    # Получаем данные из JSON-запроса
    data = request.json
    
    # Проверяем, что данные есть и содержат номер телефона
    if not data or 'phone_number' not in data:
        return jsonify({'error': 'Отсутствует номер телефона'}), 400
        
    # Нормализуем номер телефона (удаляем все нецифровые символы)
    phone_number = normalize_phone_number(data['phone_number'])
    
    # Проверка длины номера телефона (минимум 10 цифр)
    if not phone_number or len(phone_number) < 10:
        return jsonify({'error': 'Некорректный номер телефона. Номер должен содержать не менее 10 цифр.'}), 400
    
    # Проверяем, существует ли уже пользователь с таким номером
    existing_user = User.query.filter_by(phone_number=phone_number).first()
    if existing_user:
        return jsonify({'error': 'Пользователь с таким номером телефона уже существует'}), 409
    
    # Создаем нового пользователя
    user = User(phone_number=phone_number)
    
    # Устанавливаем пароль, если он предоставлен
    if 'password' in data:
        user.set_password(data['password'])
    else:
        # Генерируем случайный пароль для пользователей, зарегистрированных через API
        random_password = secrets.token_hex(8)
        user.set_password(random_password)
        # Возвращаем сгенерированный пароль, если он был создан автоматически
        data['generated_password'] = random_password
    
    # Сохраняем пользователя в базу данных
    db.session.add(user)
    db.session.commit()
    
    # Формируем ответ с данными пользователя
    result = {
        'id': user.id,
        'phone_number': user.phone_number
    }
    
    # Добавляем сгенерированный пароль в результат, если он есть
    if 'generated_password' in data:
        result['generated_password'] = data['generated_password']
    
    return jsonify(result), 201

# Вход пользователя через API
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    # Получаем данные из JSON-запроса
    data = request.json
    
    # Проверяем, что данные есть
    if not data:
        return jsonify({'error': 'Отсутствуют данные для входа'}), 400
    
    # Вход по номеру телефона и паролю
    if 'phone_number' in data and 'password' in data:
        # Нормализуем номер телефона (удаляем все нецифровые символы)
        phone_number = normalize_phone_number(data['phone_number'])
        
        # Проверка длины номера телефона (минимум 10 цифр)
        if not phone_number or len(phone_number) < 10:
            return jsonify({'error': 'Некорректный номер телефона. Номер должен содержать не менее 10 цифр.'}), 400
        
        # Ищем пользователя по номеру телефона
        user = User.query.filter_by(phone_number=phone_number).first()
        
        # Проверяем, что пользователь существует и пароль верный
        if user and user.check_password(data['password']):
            return jsonify({
                'id': user.id,
                'phone_number': user.phone_number
            }), 200
    
    return jsonify({'error': 'Неверные учетные данные'}), 401

# Получение информации о пользователе по ID
@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    # Находим пользователя по ID или возвращаем 404, если не найден
    user = User.query.get_or_404(user_id)
    
    # Возвращаем данные пользователя
    return jsonify({
        'id': user.id,
        'phone_number': user.phone_number
    }), 200

# Получение настроений пользователя через API
@app.route('/api/user/<int:user_id>/moods', methods=['GET'])
def get_user_moods_api(user_id):
    # Находим пользователя по ID или возвращаем 404, если не найден
    user = User.query.get_or_404(user_id)
    
    # Получаем параметры фильтрации из запроса
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    hours = request.args.get('hours', type=float)
    emojis_param = request.args.get('emojis')
    
    # Обработка списка эмодзи, если он предоставлен
    emojis = None
    if emojis_param:
        emojis = emojis_param.split(',')
    
    # Получаем настроения пользователя из базы
    user_moods_query = Mood.query.filter_by(user_id=user.id)
    
    # Применяем фильтр по времени, если указан
    if hours:
        cutoff_time = datetime.utcnow() - timedelta(hours=float(hours))
        user_moods_query = user_moods_query.filter(Mood.timestamp > cutoff_time)
    
    # Сортируем по времени (сначала новые)
    user_moods = user_moods_query.order_by(Mood.timestamp.desc()).all()
    
    # Форматируем настроения для API-ответа
    result = [{
        'id': mood.id,
        'emoji': mood.emoji,
        'text': mood.text or '',
        'latitude': mood.latitude,
        'longitude': mood.longitude,
        'timestamp': mood.timestamp.isoformat()
    } for mood in user_moods]
    
    # Применяем фильтр по эмодзи, если указан
    if emojis and len(emojis) > 0:
        result = [mood for mood in result if mood['emoji'] in emojis]
    
    # Применяем фильтр по местоположению, если указаны все необходимые параметры
    if lat is not None and lng is not None and radius is not None:
        analyzer = MoodAnalyzer([])  # Создаем экземпляр только для использования функции расчета расстояния
        result = [
            mood for mood in result 
            if analyzer._calculate_distance(lat, lng, mood['latitude'], mood['longitude']) <= radius
        ]
    
    return jsonify(result)

@app.route('/api/moods', methods=['POST'])
def create_mood():
    # Получаем данные из запроса
    data = request.json
    
    if not data:
        return jsonify({'error': 'Отсутствуют данные настроения'}), 400
    
    # Проверяем обязательные поля
    if not all(key in data for key in ['emoji', 'latitude', 'longitude']):
        return jsonify({'error': 'Отсутствуют обязательные поля: emoji, latitude, longitude'}), 400
    
    # Определяем пользователя
    user_id = None
    
    # Если пользователь аутентифицирован через flask-login
    if current_user.is_authenticated:
        user_id = current_user.id
    # Если user_id передан в запросе (API запрос)
    elif 'user_id' in data:
        user_id = data['user_id']
        # Проверяем, существует ли пользователь
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404
    else:
        # Если пользователь не аутентифицирован и user_id не передан,
        # возвращаем ошибку
        return jsonify({'error': 'Необходима аутентификация или указание user_id'}), 401
    
    # Создаем запись настроения
    mood = Mood(
        emoji=data['emoji'],
        text=data.get('text', ''),
        latitude=data['latitude'],
        longitude=data['longitude'],
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    
    # Сохраняем запись в базу данных
    db.session.add(mood)
    db.session.commit()
    
    # Возвращаем данные о созданной записи
    return jsonify({
        'id': mood.id,
        'emoji': mood.emoji,
        'text': mood.text,
        'latitude': mood.latitude,
        'longitude': mood.longitude,
        'timestamp': mood.timestamp.isoformat(),
        'user_id': mood.user_id
    }), 201

@app.route('/api/moods/<int:mood_id>', methods=['DELETE'])
def delete_mood(mood_id):
    # Находим запись настроения по ID или возвращаем 404, если не найдена
    mood = Mood.query.get_or_404(mood_id)
    
    # Проверка прав доступа
    if current_user.is_authenticated:
        # Если пользователь аутентифицирован через flask-login
        if mood.user_id != current_user.id:
            return jsonify({'error': 'Нет прав на удаление этого настроения'}), 403
    else:
        # Для API запросов проверяем user_id в параметрах запроса
        user_id = request.args.get('user_id', type=int)
        if not user_id or mood.user_id != user_id:
            return jsonify({'error': 'Необходима аутентификация или указание правильного user_id'}), 403
    
    # Удаляем настроение
    db.session.delete(mood)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Настроение удалено'}), 200

# Routes
@app.route('/')
def index():
    # Главная страница - перенаправляем на карту если пользователь авторизован, 
    # или на страницу входа если нет
    if current_user.is_authenticated:
        return render_template('map.html')
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Если пользователь уже авторизован, перенаправляем на главную страницу
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    # Обработка отправки формы входа
    if request.method == 'POST':
        # Получаем данные из формы
        raw_phone = request.form.get('phone_number')
        # Нормализуем номер телефона
        phone_number = normalize_phone_number(raw_phone)
        password = request.form.get('password')
        
        # Проверка длины номера телефона (минимум 10 цифр)
        if not phone_number or len(phone_number) < 10:
            flash('Некорректный номер телефона. Номер должен содержать не менее 10 цифр.')
            return redirect(url_for('login'))
        
        # Ищем пользователя по номеру телефона
        user = User.query.filter_by(phone_number=phone_number).first()
        
        # Проверяем, что пользователь существует и пароль верный
        if user is None or not user.check_password(password):
            flash('Неверный номер телефона или пароль')
            return redirect(url_for('login'))
        
        # Авторизуем пользователя
        login_user(user)
        return redirect(url_for('index'))
    
    # Отображаем страницу входа для GET-запроса
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Если пользователь уже авторизован, перенаправляем на главную страницу
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    # Обработка отправки формы регистрации
    if request.method == 'POST':
        # Получаем данные из формы
        raw_phone = request.form.get('phone_number')
        # Нормализуем номер телефона
        phone_number = normalize_phone_number(raw_phone)
        password = request.form.get('password')
        
        # Проверка длины номера телефона (минимум 10 цифр)
        if not phone_number or len(phone_number) < 10:
            flash('Некорректный номер телефона. Номер должен содержать не менее 10 цифр.')
            return redirect(url_for('register'))
        
        # Проверяем, существует ли уже пользователь с таким номером
        if User.query.filter_by(phone_number=phone_number).first():
            flash('Этот номер телефона уже зарегистрирован')
            return redirect(url_for('register'))
        
        # Создаем нового пользователя
        user = User(phone_number=phone_number)
        user.set_password(password)
        
        # Сохраняем пользователя в базу данных
        db.session.add(user)
        db.session.commit()
        
        # Автоматически авторизуем нового пользователя
        login_user(user)
        return redirect(url_for('index'))
    
    # Отображаем страницу регистрации для GET-запроса
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    # Выход пользователя из системы
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    # Получаем настроения пользователя, отсортированные по времени (сначала новые)
    hours = request.args.get('hours', type=float)
    
    # Создаем запрос на получение настроений текущего пользователя
    user_moods_query = Mood.query.filter_by(user_id=current_user.id)
    
    # Применяем фильтр по времени, если указан
    if hours:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        user_moods_query = user_moods_query.filter(Mood.timestamp > cutoff_time)
    
    # Получаем данные из базы
    user_moods = user_moods_query.order_by(Mood.timestamp.desc()).all()
    
    # Форматируем настроения для отображения - используем ISO формат для временных меток,
    # чтобы их можно было преобразовать в локальное время на фронтенде
    formatted_moods = []
    for mood in user_moods:
        formatted_moods.append({
            'id': mood.id,
            'emoji': mood.emoji,
            'text': mood.text or '',
            'latitude': mood.latitude,
            'longitude': mood.longitude,
            'timestamp': mood.timestamp.isoformat(),
            'formatted_time': mood.timestamp.isoformat()
        })
    
    # Отображаем страницу профиля с данными о настроениях
    return render_template('profile.html', moods=formatted_moods)

@app.route('/api/moods', methods=['GET'])
def get_moods():
    # Получаем параметры фильтрации из запроса
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    hours = request.args.get('hours', type=float)
    emojis_param = request.args.get('emojis')
    
    # Обработка списка эмодзи, если он предоставлен
    emojis = None
    if emojis_param:
        emojis = emojis_param.split(',')
    
    # Получение всех настроений с учетом фильтров через вспомогательную функцию
    moods_data = get_mood_data_for_api(lat, lng, radius, hours, emojis)
    
    # Возвращаем данные в формате JSON
    return jsonify(moods_data)

@app.route('/api/area-mood', methods=['GET'])
def get_area_mood():
    # Получаем параметры запроса для анализа настроений в конкретной области
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float, default=5.0)
    hours = request.args.get('hours', type=float)
    
    # Проверяем наличие обязательных параметров местоположения
    if lat is None or lng is None:
        return jsonify({'error': 'Необходимо указать параметры lat и lng'}), 400
    
    # Фильтруем настроения по времени, если указан параметр hours
    moods = get_mood_data_for_api(hours=hours)
    
    # Создаем экземпляр анализатора настроений
    analyzer = MoodAnalyzer(moods)
    
    # Получаем общее настроение для указанной области
    area_mood = analyzer.get_area_mood(lat, lng, radius)
    
    # Возвращаем результат анализа
    return jsonify(area_mood)

@app.route('/api/events', methods=['GET'])
def get_events():
    # Получаем параметры запроса для обнаружения событий
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    hours = request.args.get('hours', default=24, type=float)
    min_confidence = request.args.get('min_confidence', default=30, type=int)
    
    # Получаем настроения с учетом фильтров местоположения и времени
    moods = get_mood_data_for_api(lat, lng, radius, hours)
    
    # Создаем экземпляр анализатора настроений
    analyzer = MoodAnalyzer(moods)
    
    # Определяем возможные события на основе данных о настроениях
    events = analyzer.detect_events()
    
    # Фильтруем события по уровню достоверности
    if min_confidence > 0:
        events = [event for event in events if event['confidence'] >= min_confidence]
    
    # Возвращаем найденные события
    return jsonify(events)

@app.route('/api/trends', methods=['GET'])
def get_trends():
    # Получаем параметры запроса для анализа трендов настроений
    hours = request.args.get('hours', default=24, type=int)
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    
    # Получаем настроения с учетом фильтров местоположения
    moods = get_mood_data_for_api(lat, lng, radius)
    
    # Создаем экземпляр анализатора настроений
    analyzer = MoodAnalyzer(moods)
    
    # Получаем тренды настроений за указанный период времени
    trends = analyzer.get_mood_trends(hours)
    
    # Добавляем общее количество настроений в результат
    trends['total_moods'] = len(moods)
    
    # Возвращаем данные о трендах
    return jsonify(trends)

@app.route('/api/user-moods', methods=['GET'])
def get_user_moods():
    # Определяем ID пользователя для запроса настроений
    user_id = None
    
    # Если пользователь аутентифицирован через flask-login, используем его ID
    if current_user.is_authenticated:
        user_id = current_user.id
    # Если user_id передан в параметрах запроса, используем его
    else:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'Необходима аутентификация или указание user_id'}), 401
    
    # Получаем параметры фильтрации из запроса
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', type=float)
    hours = request.args.get('hours', type=float)
    emojis_param = request.args.get('emojis')
    
    # Обработка списка эмодзи, если он предоставлен
    emojis = None
    if emojis_param:
        emojis = emojis_param.split(',')
    
    # Получаем данные о пользователе или возвращаем 404, если не найден
    user = User.query.get_or_404(user_id)
    # Создаем запрос на получение настроений этого пользователя
    user_moods_query = Mood.query.filter_by(user_id=user.id)
    
    # Применяем фильтр по времени, если указан
    if hours:
        cutoff_time = datetime.utcnow() - timedelta(hours=float(hours))
        user_moods_query = user_moods_query.filter(Mood.timestamp > cutoff_time)
    
    # Сортируем по времени (сначала новые)
    user_moods = user_moods_query.order_by(Mood.timestamp.desc()).all()
    
    # Форматируем настроения для API-ответа
    result = [{
        'id': mood.id,
        'emoji': mood.emoji,
        'text': mood.text or '',
        'latitude': mood.latitude,
        'longitude': mood.longitude,
        'timestamp': mood.timestamp.isoformat()
    } for mood in user_moods]
    
    # Применяем фильтр по эмодзи, если указан
    if emojis and len(emojis) > 0:
        result = [mood for mood in result if mood['emoji'] in emojis]
    
    # Применяем фильтр по местоположению, если указаны все необходимые параметры
    if lat is not None and lng is not None and radius is not None:
        analyzer = MoodAnalyzer([])  # Создаем экземпляр только для использования функции расчета расстояния
        result = [
            mood for mood in result 
            if analyzer._calculate_distance(lat, lng, mood['latitude'], mood['longitude']) <= radius
        ]
    
    # Возвращаем отфильтрованные настроения пользователя
    return jsonify(result)

if __name__ == '__main__':
    # Создаем все таблицы в базе данных при запуске приложения
    with app.app_context():
        db.create_all()
    # Запускаем приложение в режиме отладки, доступное со всех сетевых интерфейсов
    app.run(debug=True, host='0.0.0.0') 