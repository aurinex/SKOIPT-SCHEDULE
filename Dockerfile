# ========== Базовый образ ========== 
FROM python:3.11-slim

# ========== Переменные окружения ==========
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ========== Рабочая директория ==========
WORKDIR /app

# ========== Установка зависимостей ==========
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ========== Копирование исходного кода ==========
COPY . .

# ========== Порт (если нужно для API или healthcheck) ==========
EXPOSE 3020

# ========== Запуск ==========
CMD ["python", "bot.py"]