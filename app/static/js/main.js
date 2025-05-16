// Обработчик всплывающих сообщений
document.addEventListener('DOMContentLoaded', function() {
    // Автоматически скрываем всплывающие сообщения через 3 секунды
    const flashMessages = document.querySelectorAll('.flash-message');
    
    if (flashMessages.length > 0) {
        setTimeout(function() {
            flashMessages.forEach(message => {
                message.style.opacity = '0'; // Делаем сообщение прозрачным
                setTimeout(() => {
                    message.remove(); // Удаляем сообщение из DOM после анимации
                }, 500);
            });
        }, 3000);
    }
});

// Набор полезных функций для работы с приложением
const MoodMapUtils = {
    // Получение смещения часового пояса пользователя в минутах
    // (нужно для правильного отображения времени)
    getUserTimezoneOffset: function() {
        return new Date().getTimezoneOffset();
    },
    
    // Преобразование времени из UTC (всемирного времени) в локальное время пользователя
    // dateString - строка с датой в формате ISO (например, "2023-05-20T14:30:00")
    convertToUserTimezone: function(dateString) {
        // Добавляем 'Z' в конец строки, чтобы указать, что это время в UTC
        const date = new Date(dateString + 'Z');
        return date;
    },
    
    // Форматирование даты для отображения в удобном виде (дата и время)
    formatDate: function(dateString) {
        const date = this.convertToUserTimezone(dateString);
        return date.toLocaleString(); // Преобразует в формат "ДД.ММ.ГГГГ, ЧЧ:ММ:СС"
    },
    
    // Форматирование даты, показывая только время
    formatTime: function(dateString) {
        const date = this.convertToUserTimezone(dateString);
        return date.toLocaleTimeString(); // Преобразует в формат "ЧЧ:ММ:СС"
    },
    
    // Форматирование даты, показывая только дату без времени
    formatShortDate: function(dateString) {
        const date = this.convertToUserTimezone(dateString);
        return date.toLocaleDateString(); // Преобразует в формат "ДД.ММ.ГГГГ"
    },
    
    // Вычисляет, сколько минут прошло между текущим временем и указанной датой
    // Используется для фильтрации по времени ("за последние 30 минут" и т.д.)
    getMinutesDifference: function(timestamp) {
        const now = new Date(); // Текущее время
        const date = this.convertToUserTimezone(timestamp); // Указанное время
        return Math.floor((now - date) / (1000 * 60)); // Разница в миллисекундах / (1000 * 60) = минуты
    },
    
    // Проверяет, находится ли дата в указанном временном интервале
    isWithinTimeFrame: function(timestamp, minutes) {
        if (!minutes) return true; // Если интервал не указан, считаем, что дата подходит
        
        try {
            const diffMinutes = this.getMinutesDifference(timestamp);
            return diffMinutes <= minutes; // Возвращает true, если разница меньше или равна указанному интервалу
        } catch (e) {
            console.error('Ошибка при проверке временного интервала:', e);
            return true; // В случае ошибки считаем, что дата подходит
        }
    },
    
    // Вычисляет расстояние между двумя точками на Земле в километрах
    // Использует формулу гаверсинуса для учета сферичности Земли
    calculateDistance: function(lat1, lon1, lat2, lon2) {
        const R = 6371; // Радиус Земли в километрах
        const dLat = this.deg2rad(lat2 - lat1); // Разница широт в радианах
        const dLon = this.deg2rad(lon2 - lon1); // Разница долгот в радианах
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(this.deg2rad(lat1)) * Math.cos(this.deg2rad(lat2)) * 
            Math.sin(dLon/2) * Math.sin(dLon/2); 
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)); 
        const d = R * c; // Расстояние в километрах
        return d;
    },
    
    // Преобразует градусы в радианы
    // Нужно для расчета расстояний, так как тригонометрические функции работают с радианами
    deg2rad: function(deg) {
        return deg * (Math.PI/180); // Градусы * (Пи/180) = радианы
    },
    
    // Определяет преобладающее настроение из коллекции настроений
    // Возвращает эмодзи, которое встречается чаще всего
    getDominantMood: function(moods) {
        const moodCounts = {}; // Объект для подсчета количества каждого эмодзи
        let maxCount = 0; // Максимальное количество
        let dominantMood = null; // Преобладающее настроение
        
        moods.forEach(mood => {
            if (!moodCounts[mood.emoji]) {
                moodCounts[mood.emoji] = 0; // Инициализируем счетчик, если эмодзи встречается впервые
            }
            moodCounts[mood.emoji]++; // Увеличиваем счетчик для этого эмодзи
            
            if (moodCounts[mood.emoji] > maxCount) {
                maxCount = moodCounts[mood.emoji]; // Обновляем максимальное количество
                dominantMood = mood.emoji; // Запоминаем преобладающее эмодзи
            }
        });
        
        return dominantMood; // Возвращаем преобладающее эмодзи
    },
    
    // Вычисляет процент позитивных настроений
    // Возвращает число от 0 до 100, где 100 - все настроения позитивные
    getMoodPercentage: function(moods) {
        if (!moods || moods.length === 0) return 50; // Если нет настроений, возвращаем 50% (нейтрально)
        
        const positiveEmojis = ['😊', '😎', '🥰']; // Список позитивных эмодзи
        const negativeEmojis = ['😢', '😡', '😷']; // Список негативных эмодзи
        
        let positiveCount = 0;
        let negativeCount = 0;
        
        moods.forEach(mood => {
            if (positiveEmojis.includes(mood.emoji)) {
                positiveCount++;
            } else if (negativeEmojis.includes(mood.emoji)) {
                negativeCount++;
            }
        });
        
        const total = positiveCount + negativeCount; // Общее количество настроений
        if (total === 0) return 50; // Если нет ни позитивных, ни негативных настроений, возвращаем 50%
        
        return Math.round((positiveCount / total) * 100); // Вычисляем процент позитивных настроений
    },
    
    // Проверяет, находится ли точка в пределах указанного радиуса от центра
    // Используется для фильтрации настроений по расстоянию от пользователя
    isWithinRadius: function(centerLat, centerLng, pointLat, pointLng, radiusKm) {
        const distance = this.calculateDistance(centerLat, centerLng, pointLat, pointLng);
        return distance <= radiusKm; // Возвращает true, если расстояние меньше или равно радиусу
    },
    
    // Генерирует случайное смещение для обеспечения конфиденциальности
    // Используется, чтобы не показывать точные координаты пользователей на карте
    getPrivacyOffset: function() {
        return (Math.random() - 0.5) * 0.002; // Примерно 100-200 метров смещения в случайном направлении
    }
};