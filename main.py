import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import instaloader
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Константы
DOWNLOADS_DIR = Path("downloads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ
logger = logging.getLogger(__name__)

class VideoDownloader:
    """Класс для управления загрузкой видео"""

    def __init__(self):
        self._ensure_downloads_dir()

    def _ensure_downloads_dir(self) -> None:
        """Создает директорию для загрузок, если она не существует"""
        DOWNLOADS_DIR.mkdir(exist_ok=True)

    async def download_youtube(self, url: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Скачивает видео с YouTube"""
        await update.message.reply_text("Начинаю скачивание видео с YouTube...")

        ydl_opts = {
            'format': 'best[filesize<50M][ext=mp4]/best[filesize<50M]/best',
            'outtmpl': str(DOWNLOADS_DIR / '%(title)s.%(ext)s'),
            'max_filesize': MAX_FILE_SIZE,
        }

        file_path = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dict)
                file_path = Path(filename)

                logger.info(f"Попытка скачать файл: {file_path}")

                if file_path.exists():
                    # Проверяем размер файла перед отправкой
                    file_size = file_path.stat().st_size
                    logger.info(f"Размер файла: {file_size / 1024 / 1024:.1f} МБ")

                    if file_size > MAX_FILE_SIZE:
                        await update.message.reply_text(
                            f"Видео слишком большое ({file_size / 1024 / 1024:.1f} МБ). "
                            f"Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024} МБ"
                        )
                        return


                    with open(file_path, 'rb') as video:
                        await context.bot.send_video(
                            chat_id=update.effective_chat.id,
                            video=video,
                            supports_streaming=True
                        )

                    await update.message.reply_text("Видео успешно скачано и отправлено!")
                else:
                    await update.message.reply_text("Не удалось найти скачанный файл.")

        except yt_dlp.DownloadError as e:
            logger.error(f"Ошибка скачивания с YouTube: {e}")
            await update.message.reply_text("Не удалось скачать видео с YouTube. Проверьте ссылку.")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при работе с YouTube: {e}")
            await update.message.reply_text("Произошла ошибка при обработке видео.")
        finally:
            # Удаляем файл если он существует
            if file_path and file_path.exists():
                file_path.unlink()
                logger.info(f"Файл удален: {file_path}")

    async def download_instagram(self, url: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Скачивает видео с Instagram"""
        await update.message.reply_text("Начинаю скачивание видео с Instagram...")

        target_dir = None

        try:
            L = instaloader.Instaloader(
                download_videos=True,
                download_pictures=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                dirname_pattern = str(DOWNLOADS_DIR / "{shortcode}"),
                filename_pattern = "{shortcode}"
            )

            shortcode = self._extract_instagram_shortcode(url)
            if not shortcode:
                await update.message.reply_text("Неверная ссылка на Instagram.")
                return

            logger.info(f"Shortcode: {shortcode}")

            post = instaloader.Post.from_shortcode(L.context, shortcode)
            target_dir = DOWNLOADS_DIR / shortcode

            logger.info(f"Целевая директория: {target_dir}")

            # Скачиваем пост
            L.download_post(post, target=str(target_dir))

            # Ищем видеофайл
            video_file = self._find_video_file(target_dir)
            logger.info(f"Найденный видеофайл: {video_file}")

            if video_file and video_file.exists():
                file_size = video_file.stat().st_size
                logger.info(f"Размер видео: {file_size / 1024 / 1024:.1f} МБ")

                if file_size > MAX_FILE_SIZE:
                    await update.message.reply_text(
                        f"Видео слишком большое ({file_size / 1024 / 1024:.1f} МБ). "
                        f"Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024} МБ"
                    )
                else:
                    try:
                        with open(video_file, 'rb') as video:
                            await context.bot.send_video(
                                chat_id=update.effective_chat.id,
                                video=video,
                                supports_streaming=True
                            )
                        await update.message.reply_text("Видео успешно скачано и отправлено!")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке видео: {e}")
                        await update.message.reply_text(f"Произошла ошибка при отправке видео: {str(e)}")
            else:
                await update.message.reply_text("В этом посте нет видео или оно недоступно.")

        except instaloader.exceptions.InstaloaderException as e:
            logger.error(f"Ошибка Instagram загрузчика: {e}")
            await update.message.reply_text("Не удалось скачать видео с Instagram. Возможно, пост приватный или удалён.")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при работе с Instagram: {e}")
            await update.message.reply_text("Произошла ошибка при обработке Instagram видео.")
        finally:
            # Всегда очищаем директорию если она существует
            if target_dir and target_dir.exists():
                shutil.rmtree(target_dir)
                logger.info(f"Директория {target_dir} очищена")

    def _extract_instagram_shortcode(self, url: str) -> Optional[str]:
        """Извлекает shortcode из Instagram URL"""
        try:
            # Обрабатываем различные форматы URL
            if "/reel/" in url:
                return url.split("/reel/")[-1].split("/")[0].split("?")[0]
            elif "/p/" in url:
                return url.split("/p/")[-1].split("/")[0].split("?")[0]
            elif "/reels/" in url:
                return url.split("/reels/")[-1].split("/")[0].split("?")[0]
            else:
                return url.split("/")[-2] if len(url.split("/")) > 4 else None
        except Exception:
            return None

    def _find_video_file(self, directory: Path) -> Optional[Path]:
        """Ищет видео файл в директории (включая подпапки)"""
        if not directory.exists():
            logger.warning(f"Директория не существует: {directory}")
            return None

        logger.info(f"Поиск видео в директории (рекурсивно): {directory}")

        # Рекурсивный поиск всех .mp4 и .mov файлов
        video_files = list(directory.rglob("*.mp4")) + list(directory.rglob("*.mov"))

        for vf in video_files:
            logger.info(f"Найден видеофайл: {vf} (размер: {vf.stat().st_size} байт)")

        # Сортируем по размеру (на случай, если есть превьюшки) — берём самый большой
        if video_files:
            return max(video_files, key=lambda f: f.stat().st_size)

        return None

class TelegramBot:
    """Основной класс Telegram бота"""

    def __init__(self):
        self.downloader = VideoDownloader()
        self.token = os.getenv("BOT_TOKEN")

        if not self.token:
            raise ValueError("Токен не найден. Установите переменную окружения BOT_TOKEN.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        await update.message.reply_text(
            "🎬 *Привет! Я бот для скачивания видео*\n\n"
            "Отправь мне ссылку на видео из:\n"
            "• YouTube\n"
            "• Instagram (посты с видео и Reels)\n\n"
            "⚠️ *Важно:* Размер видео ограничен 50 МБ",
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        await update.message.reply_text(
            "📥 *Как использовать бота:*\n\n"
            "1. Скопируй ссылку на видео\n"
            "2. Отправь её мне в чат\n"
            "3. Подожди немного\n"
            "4. Получи видео в ответ\n\n"
            "💡 *Поддерживаемые платформы:*\n"
            "• YouTube\n"
            "• Instagram (посты, Reels)\n\n"
            "📁 *Ограничения:*\n"
            "• Максимальный размер: 50 МБ\n"
            "• Форматы: MP4, MOV",
            parse_mode='Markdown'
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик текстовых сообщений"""
        if not update.message or not update.message.text:
            return

        url = update.message.text.strip()

        # Проверяем, является ли сообщение ссылкой
        if not (url.startswith('http://') or url.startswith('https://')):
            await update.message.reply_text("Пожалуйста, отправь мне ссылку на видео.")
            return

        # Определяем тип ссылки и обрабатываем
        if any(domain in url for domain in ['youtube.com', 'youtu.be']):
            await self.downloader.download_youtube(url, update, context)
        elif 'instagram.com' in url:
            await self.downloader.download_instagram(url, update, context)
        else:
            await update.message.reply_text(
                "⚠️ Эта платформа пока не поддерживается.\n\n"
                "Поддерживаемые платформы:\n"
                "• YouTube\n"
                "• Instagram"
            )

    def run(self) -> None:
        """Запуск бота"""
        application = Application.builder().token(self.token).build()

        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Бот запущен и готов к работе...")
        application.run_polling()


def main() -> None:
    """Основная функция"""
    try:
        bot = TelegramBot()
        bot.run()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")


if __name__ == "__main__":
    main()