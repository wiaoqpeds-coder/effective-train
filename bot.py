import logging
import os
import re
import tempfile

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

# ==== НАСТРОЙКИ ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER")

# Если используешь свой локальный Bot API сервер (telegram-bot-api), укажи его адрес,
# например: https://my-bot-api-server.up.railway.app
# Если переменная не задана — бот работает через официальный облачный API Telegram
# и лимит на отправку файла составляет 50 МБ.
LOCAL_BOT_API_URL = os.environ.get("LOCAL_BOT_API_URL", "").rstrip("/")

# Лимит размера файла в МБ. Если задан LOCAL_BOT_API_URL, можно поднять почти до 2000.
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "2000" if LOCAL_BOT_API_URL else "50"))

YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+"
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли мне ссылку на видео с YouTube — я скачаю и пришлю файл.\n\n"
        f"Учти: Telegram не даёт ботам отправлять файлы больше {MAX_FILE_SIZE_MB} МБ, "
        "поэтому для длинных видео качество будет снижено автоматически."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = YOUTUBE_RE.search(text)

    if not match:
        await update.message.reply_text("Пришли, пожалуйста, ссылку на видео с YouTube.")
        return

    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    status_msg = await update.message.reply_text("Скачиваю видео, подожди немного...")
    await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)

    with tempfile.TemporaryDirectory() as tmpdir:
        outtemplate = os.path.join(tmpdir, "%(title).80s.%(ext)s")

        # Формат подобран так, чтобы стараться уложиться в лимит размера
        ydl_opts = {
            "outtmpl": outtemplate,
            "format": (
                f"best[filesize<{MAX_FILE_SIZE_MB}M][ext=mp4]/"
                f"best[filesize_approx<{MAX_FILE_SIZE_MB}M][ext=mp4]/"
                "worst[ext=mp4]/worst"
            ),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)
        except Exception as e:
            log.exception("Ошибка скачивания")
            await status_msg.edit_text(f"Не получилось скачать видео: {e}")
            return

        if not os.path.exists(filepath):
            # иногда yt-dlp меняет расширение после merge
            base, _ = os.path.splitext(filepath)
            candidates = [f for f in os.listdir(tmpdir) if f.startswith(os.path.basename(base))]
            if candidates:
                filepath = os.path.join(tmpdir, candidates[0])

        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        if size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"Видео весит {size_mb:.1f} МБ — это больше лимита Telegram ({MAX_FILE_SIZE_MB} МБ). "
                "Не могу отправить файл, попробуй другое видео покороче."
            )
            return

        await status_msg.edit_text("Загружаю в Telegram...")
        try:
            with open(filepath, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    caption=info.get("title", ""),
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )
            await status_msg.delete()
        except Exception as e:
            log.exception("Ошибка отправки")
            await status_msg.edit_text(f"Скачал, но не смог отправить файл: {e}")


def main():
    if BOT_TOKEN == "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER":
        raise SystemExit(
            "Укажи токен бота в переменной окружения BOT_TOKEN или прямо в коде (BOT_TOKEN=...)."
        )

    builder = Application.builder().token(BOT_TOKEN)
    if LOCAL_BOT_API_URL:
        # Подключаемся к своему Bot API серверу вместо облачного api.telegram.org
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot").base_file_url(
            f"{LOCAL_BOT_API_URL}/file/bot"
        )
        log.info("Использую локальный Bot API сервер: %s", LOCAL_BOT_API_URL)

    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
