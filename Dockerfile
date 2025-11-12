# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для yt-dlp и instaloader
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем директорию для загрузок
RUN mkdir -p downloads

CMD ["python", "bot.py"]