# bot.py
import logging
import os
import subprocess
import instaloader
import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
load_dotenv()

# Функция для команды /start


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Отправь мне ссылку на видео из YouTube или Instagram, и я его скачаю."
    )


# Функция для команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Просто отправь мне ссылку на видео.\n"
        "Я поддерживаю:\n"
        "- YouTube\n"
        "- Instagram (посты с видео и Reels)"
    )


# Функция для скачивания видео с YouTube
async def download_youtube(
    url: str, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text("Начинаю скачивание видео с YouTube...")

    # Создаем директорию, если она не существует
    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "format": "best[filesize<50M]",
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info_dict)

        # Проверяем существование файла
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Файл не найден: {filename}")

        with open(filename, "rb") as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id, video=video_file
            )

        # Удаляем файл после успешной отправки
        os.remove(filename)
        await update.message.reply_text("Готово!")

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Ошибка скачивания: {e}")
        await update.message.reply_text(
            "Не удалось скачать видео. Попробуйте другой URL."
        )
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {e}")
        await update.message.reply_text("Ошибка: файл не был создан.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")


# Функция для скачивания видео с Instagram


async def download_instagram(
    url: str, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text("Начинаю скачивание видео с Instagram...")

    L = instaloader.Instaloader(
        download_videos=True,
        download_pictures=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    # Извлекаем shortcode из URL
    shortcode = url.split("/")[-2]
    if not shortcode:
        await update.message.reply_text("Неверная ссылка на Instagram.")
        return

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        # Скачиваем в временную директорию, чтобы не засорять
        L.download_post(post, target=f"downloads/{shortcode}")

        # Ищем видеофайл в директории
        for filename in os.listdir(f"downloads/{shortcode}"):
            if filename.endswith(".mp4"):
                filepath = f"downloads/{shortcode}/{filename}"
                await context.bot.send_video(
                    chat_id=update.effective_chat.id, video=open(
                        filepath, "rb")
                )
                await update.message.reply_text("Готово!")
                # Удаляем директорию с файлом
                subprocess.run(["rm", "-rf", f"downloads/{shortcode}"])
                return

        await update.message.reply_text("В этом посте нет видео.")
    except Exception as e:
        logger.error(f"Ошибка при скачивании с Instagram: {e}")
        await update.message.reply_text(f"Не удалось скачать видео. Ошибка: {e}")


# Основной обработчик сообщений


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text
    if "youtube.com" in url or "youtu.be" in url:
        await download_youtube(url, update, context)
    elif "instagram.com" in url:
        await download_instagram(url, update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, отправь мне ссылку на YouTube или Instagram."
        )


def main() -> None:
    # Создаем директорию для загрузок, если ее нет
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error(
            "Токен не найден. Установите переменную окружения TELEGRAM_TOKEN.")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
