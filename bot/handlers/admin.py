import asyncio
from threading import Thread
from telebot import types
from bot.core import bot
from bot.handlers.commands import is_admin
from bot.utils.api import (
    api_get_users, api_get_users_page_peek, api_update_user
)

def render_admin_panel(chat_id: int, message_id: int | None = None):
    text = "👑 Панель администратора\n\nВыберите действие:"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users"))
    kb.add(types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.add(types.InlineKeyboardButton("🔄 Обновить расписание", callback_data="admin_refresh"))
    kb.add(types.InlineKeyboardButton("🔔 Обновить расписание звонков", callback_data="admin_refresh_bell"))
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = int(message.from_user.id)
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав для доступа к этой команде.")
        return
    render_admin_panel(user_id)
    
@bot.callback_query_handler(func=lambda call: call.data == "admin_refresh_bell")
def admin_refresh_bell(call):
    """Админ обновляет расписание звонков"""
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return

    bot.answer_callback_query(call.id, "📤 Отправьте JSON-файл с расписанием звонков")
    msg = bot.send_message(
        user_id,
        "📤 Отправьте JSON-файл `bell_schedule.json` или другой файл в том же формате.\n"
        "Он будет отправлен на сервер и применён ко всем расписаниям."
    )
    bot.register_next_step_handler(msg, process_bell_schedule_upload)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callback_handler(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return
    
    if call.data.startswith("admin_users"):
        try: bot.answer_callback_query(call.id)
        except: pass

        parts = call.data.split(":")
        skip = int(parts[1]) if len(parts) > 1 else 0
        limit = int(parts[2]) if len(parts) > 2 else 10
        show_user_management(call, skip=skip, limit=limit)
        return

    if call.data == "admin_users":
        show_user_management(call)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_stats":
        show_admin_stats(call)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_refresh":
        bot.answer_callback_query(call.id, "Загрузите DOCX-файл расписания сообщением — я отправлю его на сервер")
        bot.send_message(user_id, "📤 Отправьте DOCX-файл расписания.\n(Необязательно) Следом отправьте JSON со сменами `group_shifts.json`. Я загружу оба файла на сервер.")
    elif call.data == "admin_panel":
        render_admin_panel(user_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_set_teacher":
        set_teacher_callback(call)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_back":
        render_admin_panel(user_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)
        
def process_bell_schedule_upload(message):
    """Принимает JSON и отправляет его на API /bell/upload"""
    user_id = message.from_user.id

    if message.content_type != "document":
        bot.send_message(user_id, "❌ Пришлите именно JSON-файл.")
        render_admin_panel(user_id)
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        fname = message.document.file_name.lower()

        if not fname.endswith(".json"):
            bot.send_message(user_id, "❌ Это не JSON-файл.")
            render_admin_panel(user_id)
            return

        bot.send_message(user_id, "⏳ Загружаю расписание звонков на сервер...")

        from bot.utils.api import api_upload_bell_schedule
        resp = api_upload_bell_schedule(file_bytes)

        if resp:
            msg_text = f"✅ Расписание звонков успешно обновлено!\n\n"
            msg_text += "📣 Уведомить всех пользователей о новых звонках?"

            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton("✅ Да, уведомить всех", callback_data="notify_all:bell"),
                types.InlineKeyboardButton("🚫 Нет, не уведомлять", callback_data="skip_notify:bell")
            )
            bot.send_message(user_id, msg_text, reply_markup=kb)
        else:
            bot.send_message(user_id, "❌ Ошибка при загрузке расписания звонков.")
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Ошибка: {e}")
    finally:
        pass  # Панель не возвращаем сразу — ждём решения админа

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

        # небольшая пауза, чтобы не получить flood control от Telegram
        asyncio.run(asyncio.sleep(0.05))

    bot.send_message(admin_id, f"✅ Рассылка завершена! Отправлено {sent} из {total}.")
    render_admin_panel(admin_id)
    
@bot.callback_query_handler(func=lambda call: call.data.startswith("notify_all:") or call.data.startswith("skip_notify:"))
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
        render_admin_panel(user_id)
        return

    bot.answer_callback_query(call.id, f"📢 Начинаю уведомление ({context_name})...")
    from bot.utils.api import api_get_users
    users = api_get_users()

    # текст уведомления можно менять в зависимости от типа
    if context_name == "bell":
        msg_text = "🔔 Обновлено расписание звонков!"
    elif context_name == "schedule":
        msg_text = "📚 Обновлено основное расписание занятий!"
    else:
        msg_text = "📢 Новое обновление в системе!"

    # запускаем рассылку в отдельном потоке
    Thread(target=send_notification_progressively, args=(bot, users, msg_text, user_id, context_name)).start()

def show_user_management(call, skip: int = 0, limit: int = 10):
    user_id = call.from_user.id
    message_id = call.message.message_id

    skip = max(0, int(skip))
    limit = max(1, int(limit))

    rows, has_next = api_get_users_page_peek(skip=skip, limit=limit)
    if not rows and skip > 0:
        skip = max(0, skip - limit)
        rows, has_next = api_get_users_page_peek(skip=skip, limit=limit)

    from config import ROLES
    users_info = []
    for u in rows:
        uid = u.get('user_id')
        uname = u.get('username')
        role = u.get('role', 'student')
        grp = u.get('group_name') or 'нет группы'
        line = f"@{uname}, {uid}: {ROLES.get(role, role)}"
        if role == 'student':
            line += f", группа: {grp}"
        fio = u.get('teacher_fio')
        if fio:
            line += f", ФИО: {fio}"
        users_info.append(line)

    page_num = skip // limit + 1
    users_text = "\n".join(users_info) if users_info else "—"

    text = (
        "👥 Управление пользователями\n\n"
        f"Страница: {page_num}\n"
        f"Показано: {len(rows)}\n\n"
        f"{users_text}"
    )

    kb = types.InlineKeyboardMarkup(row_width=3)
    has_prev = skip > 0
    nav_buttons = []

    if has_prev:
        nav_buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"admin_users:{skip - limit}:{limit}"))
    if has_next:
        nav_buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"admin_users:{skip + limit}:{limit}"))
    
    if nav_buttons:
        kb.add(*nav_buttons)

    kb.add(types.InlineKeyboardButton("🎯 Назначить преподавателя", callback_data="admin_set_teacher"))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))

    try:
        bot.edit_message_text(text, user_id, message_id, reply_markup=kb)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

def show_admin_stats(call):
    user_id = call.from_user.id
    message_id = call.message.message_id
    users = api_get_users()
    total = len(users)
    students = sum(1 for u in users if u.get('role') == 'student')
    teachers = sum(1 for u in users if u.get('role') == 'teacher')
    admins = sum(1 for u in users if u.get('role') == 'admin')
    groups = len({u.get('group_name') for u in users if u.get('group_name')})
    subs = sum(1 for u in users if u.get('schedule_enabled'))

    stats_text = (f"📊 Статистика бота\n\n"
                  f"👥 Всего пользователей: {total}\n"
                  f"👨‍🎓 Студентов: {students}\n"
                  f"👨‍🏫 Преподавателей: {teachers}\n"
                  f"👑 Администраторов: {admins}\n"
                  f"📚 Уникальных групп у пользователей: {groups}\n"
                  f"🔔 Подписок на рассылку: {subs}")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
    bot.edit_message_text(stats_text, user_id, message_id, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_teacher")
def set_teacher_callback(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return
    msg = bot.send_message(
        user_id,
        "🎯 Назначение преподавателя\n\n"
        "Введите ID пользователя, которого хотите назначить преподавателем.\n"
        "Можно прислать несколько ID через пробел. Для отмены — напишите «отмена»."
    )
    bot.register_next_step_handler(msg, process_teacher_appointment)

def process_teacher_appointment(message):
    admin_id = message.from_user.id
    from bot.utils.api import api_update_user, api_get_users
    text = message.text.strip()

    if text.lower() in ("отмена", "cancel", "назад"):
        bot.send_message(admin_id, "⛔️ Назначение отменено.")
        render_admin_panel(admin_id)
        return

    import re
    raw_ids = re.split(r'[\,\s]+', text)
    ok, fail = [], []

    for token in raw_ids:
        if not token:
            continue
        try:
            uid = int(token)
            updated = api_update_user(uid, {"role": "teacher"})
            if updated:
                ok.append(uid)
                try:
                    bot.send_message(
                        uid,
                        "🎉 Вам назначена роль преподавателя!\n"
                        "Перезапустите бота командой /start для завершения регистрации."
                    )
                except:
                    pass
            else:
                fail.append(token)
        except:
            fail.append(token)

    if ok:
        bot.send_message(admin_id, f"✅ Назначены преподавателями: {', '.join(map(str, ok))}")
    if fail:
        bot.send_message(admin_id, f"⚠️ Не удалось обработать: {', '.join(fail)}")

    render_admin_panel(admin_id)