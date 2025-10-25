import asyncio
from threading import Thread
from bot.core import bot
from bot.handlers.commands import is_admin
from telebot import types
from bot.utils.api import api_get_users


def send_notification_progressively(bot, users, message_text: str, admin_id: int, context_name: str):
    """
    Асинхронная рассылка уведомлений пользователям с отображением прогресса.
    Работает в отдельном потоке, чтобы не блокировать основного бота.
    """
    total = len(users)
    sent = 0
    update_step = max(1, total // 10)  # обновлять каждые 10% рассылки

    status_msg = bot.send_message(admin_id, f"📤 Начинаю рассылку ({context_name})...\nОтправлено 0 из {total}")

    for u in users:
        try:
            uid = u.get("user_id")
            if not uid:
                continue
            bot.send_message(uid, message_text)
            sent += 1
        except Exception:
            pass

        if sent % update_step == 0 or sent == total:
            try:
                bot.edit_message_text(
                    f"📨 Рассылка ({context_name})...\nОтправлено {sent} из {total}",
                    admin_id,
                    status_msg.message_id
                )
            except Exception:
                pass

        asyncio.run(asyncio.sleep(0.05))  # задержка от flood control

    bot.send_message(admin_id, f"✅ Рассылка завершена! Отправлено {sent} из {total}.")
    from bot.handlers.admin import render_admin_panel
    render_admin_panel(admin_id)


def handle_mass_notification(call):
    """
    Универсальный обработчик для уведомлений (расписание, звонки и т.д.)
    Пример callback_data:
      notify_all:bell   — уведомить всех о звонках
      notify_all:schedule — уведомить всех о расписании
      skip_notify:bell  — пропустить уведомление
    """
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет прав.")
        return

    parts = call.data.split(":")
    action = parts[0]  # notify_all / skip_notify
    context_name = parts[1] if len(parts) > 1 else "update"

    if action == "skip_notify":
        bot.answer_callback_query(call.id, "⏸ Уведомления пропущены.")
        bot.send_message(user_id, f"✅ Обновление '{context_name}' завершено без уведомлений.")
        from bot.handlers.admin import render_admin_panel
        render_admin_panel(user_id)
        return

    bot.answer_callback_query(call.id, f"📢 Начинаю уведомление ({context_name})...")
    users = api_get_users()

    # Текст уведомления
    if context_name == "bell":
        msg_text = "🔔 Обновлено расписание звонков!"
    elif context_name == "schedule":
        msg_text = "📚 Обновлено основное расписание занятий!"
    else:
        msg_text = "📢 Новое обновление в системе!"

    Thread(target=send_notification_progressively, args=(bot, users, msg_text, user_id, context_name)).start()
