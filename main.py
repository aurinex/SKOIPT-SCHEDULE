import time
from bot.core import bot as telegram_bot
from bot.utils.api import check_api_connection
from scheduler import attach_and_start_scheduler

if __name__ == "__main__":
    print("🤖 Бот запущен!")
    check_api_connection()

    try:
        telegram_bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print("remove_webhook error:", e)

    # Start APScheduler
    attach_and_start_scheduler()

    # Import handlers to register them
    import bot.handlers.commands  # noqa
    import bot.handlers.admin     # noqa
    import bot.handlers.teachers  # noqa
    import bot.handlers.callbacks # noqa
    import bot.handlers.text      # noqa

    while True:
        try:
            telegram_bot.polling(
                none_stop=True,
                timeout=60,
                long_polling_timeout=60,
                allowed_updates=["message", "callback_query", "document"],
            )
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            print("🔄 Перезапуск через 10 секунд...")
            time.sleep(10)
