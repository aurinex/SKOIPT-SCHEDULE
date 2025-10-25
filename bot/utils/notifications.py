import asyncio
from threading import Thread
from bot.core import bot
from bot.handlers.commands import is_admin
from telebot import types
from bot.utils.api import api_get_users



def send_notification_progressively(bot, users, message, admin_id: int, context_name: str):
    """
    Асинхронная рассылка сообщений пользователям с отображением прогресса.
    Может отправлять текст, фото, видео, документы, стикеры и т.д.
    Работает и с простыми строками, и с объектами Message.
    """
    total = len(users)
    sent = 0
    update_step = max(1, total // 10)
    status_msg = bot.send_message(admin_id, f"📤 Начинаю рассылку ({context_name})...\nОтправлено 0 из {total}")

    is_manual = context_name == "manual_broadcast"
    prefix = "❗️Новое объявление\n\n" if is_manual else ""

    for u in users:
        try:
            uid = u.get("user_id")
            if not uid:
                continue

            # === Если просто текст (строка) ===
            if isinstance(message, str):
                bot.send_message(uid, prefix + message)
                sent += 1
                continue

            # === Если Telegram Message ===
            ctype = message.content_type
            caption = getattr(message, "caption", None) or ""

            if ctype == "text":
                bot.send_message(uid, prefix + message.text)
            elif ctype == "photo":
                bot.send_photo(uid, message.photo[-1].file_id, caption=prefix + caption)
            elif ctype == "video":
                bot.send_video(uid, message.video.file_id, caption=prefix + caption)
            elif ctype == "document":
                bot.send_document(uid, message.document.file_id, caption=prefix + caption)
            elif ctype == "sticker":
                bot.send_sticker(uid, message.sticker.file_id)
            elif ctype == "voice":
                bot.send_voice(uid, message.voice.file_id, caption=prefix + caption)
            elif ctype == "audio":
                bot.send_audio(uid, message.audio.file_id, caption=prefix + caption)
            elif ctype == "animation":
                bot.send_animation(uid, message.animation.file_id, caption=prefix + caption)
            else:
                continue

            sent += 1

        except Exception as e:
            # можно включить лог для отладки
            # print(f"Ошибка отправки пользователю {uid}: {e}")
            continue

        # обновление статуса прогресса
        if sent % update_step == 0 or sent == total:
            try:
                bot.edit_message_text(
                    f"📨 Рассылка ({context_name})...\nОтправлено {sent} из {total}",
                    admin_id,
                    status_msg.message_id
                )
            except:
                pass

        asyncio.run(asyncio.sleep(0.05))

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
