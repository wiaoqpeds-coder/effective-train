FROM aiogram/telegram-bot-api:latest

# Порт HTTP API (Railway сам подставит $PORT, поэтому используем его в CMD)
ENV TELEGRAM_LOCAL=1

CMD ["sh", "-c", "telegram-bot-api --api-id=$TG_API_ID --api-hash=$TG_API_HASH --local --http-port=${PORT:-8081}"]
