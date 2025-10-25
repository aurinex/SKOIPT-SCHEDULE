from telebot import types
from bot.core import bot
from bot.handlers.commands import is_teacher, is_admin
from bot.utils.api import api_get_user, api_get_teacher_schedule, api_get_users
from bot.utils.fio_utils import fio_full_to_initials, normalize_full_fio, is_valid_full_fio
from bot.utils.schedule_utils import get_current_day, format_teacher_schedule_for_day

@bot.message_handler(commands=['teacher'])
def teacher_command(message):
    user_id = int(message.from_user.id)
    if not is_teacher(user_id):
        bot.send_message(user_id, "❌ У вас нет прав для доступа к этой команде.")
        return
    render_teacher_panel(user_id)

def render_teacher_panel(user_id: int, message_id: int | None = None):
    text = "👨‍🏫 Панель преподавателя\n\nВыберите действие:"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📚 Мои занятия", callback_data="teacher_lessons"))
    kb.add(types.InlineKeyboardButton("👥 Мои группы", callback_data="teacher_groups"))
    if is_admin(user_id):
        kb.add(types.InlineKeyboardButton("👑 Перейти в админ-панель", callback_data="admin_panel"))
    if message_id:
        bot.edit_message_text(text, user_id, message_id, reply_markup=kb)
    else:
        bot.send_message(user_id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith('teacher_'))
def teacher_callback_handler(call):
    user_id = call.from_user.id
    if not is_teacher(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return

    if call.data == "teacher_lessons":
        try:
            bot.clear_step_handler_by_chat_id(call.from_user.id)
        except Exception:
            pass
        user = api_get_user(user_id) or {}
        teacher_fio = user.get("teacher_fio", "Не указано")
        fio_key = fio_full_to_initials(teacher_fio)
        today = get_current_day()

        if not today:
            bot.answer_callback_query(call.id)
            bot.send_message(user_id, "🎉 Сегодня воскресенье — занятий нет.")
            return

        sch = api_get_teacher_schedule(fio_key) or {}
        schedule = sch.get("schedule", {})

        groups = set()
        for _, shift_data in schedule.items():
            day_lessons = shift_data.get(today, {})
            for _, info in day_lessons.items():
                group = info.get("group")
                if group:
                    groups.add(group)

        kb = types.InlineKeyboardMarkup(row_width=2)
        if groups:
            for g in sorted(groups):
                kb.add(types.InlineKeyboardButton(g, callback_data=f"teacher_sendtask_{g}"))
            kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="teacher_back"))

            bot.edit_message_text(
                f"👨‍🏫 Мои занятия\n\n"
                f"{teacher_fio}, выберите группу для отправки задания:",
                user_id,
                call.message.message_id,
                reply_markup=kb
            )
        else:
            kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="teacher_back"))
            bot.edit_message_text(
                f"👨‍🏫 Мои занятия\n\n"
                f"{teacher_fio}, у вас сегодня ({today}) занятий нет.",
                user_id,
                call.message.message_id,
                reply_markup=kb
            )

        bot.answer_callback_query(call.id)
        return

    elif call.data == "teacher_groups":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="teacher_back"))
        bot.edit_message_text(
            "👥 Мои группы\n\n"
            "Здесь будет список ваших групп...",
            user_id,
            call.message.message_id,
            reply_markup=kb
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "teacher_settings":
        show_teacher_settings(call)
        bot.answer_callback_query(call.id)
        return
    
    elif call.data == "teacher_change_fio":
        try:
            bot.clear_step_handler_by_chat_id(user_id)
        except Exception:
            pass
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="settings_back"))
        msg = bot.send_message(
            user_id,
            "✏️ Изменение ФИО\n\nВведите ваше новое ФИО полностью (например: Иванов Иван Иванович):",
            reply_markup=kb
        )
        bot.register_next_step_handler(msg, process_teacher_fio_change)
        bot.answer_callback_query(call.id)
        return

    elif call.data == "teacher_back":
        render_teacher_panel(user_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    elif call.data.startswith("teacher_sendtask_"):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="teacher_lessons")) 
        group = call.data.replace("teacher_sendtask_", "")
        msg = bot.send_message(
            user_id,
            f"📎 Прикрепите файл с заданием для группы *{group}* (документ, фото, архив и т.п.):",
            parse_mode="Markdown",
            reply_markup=kb
        )
        bot.register_next_step_handler(msg, lambda m: process_teacher_task_file(m, group))
        bot.answer_callback_query(call.id)
        return

def show_teacher_settings(call):
    user_id = call.from_user.id
    from bot.utils.api import api_get_user
    teacher_fio = (api_get_user(user_id) or {}).get('teacher_fio') or "Не указано"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✏️ Изменить ФИО", callback_data="teacher_change_fio"))
    keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="settings_back"))
    bot.edit_message_text(
        f"👨‍🏫 Настройки преподавателя\n\n"
        f"Текущее ФИО: {teacher_fio}",
        user_id, call.message.message_id, reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "settings_back")
def settings_back_handler(call):
    from bot.handlers.commands import render_settings_panel
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    bot.delete_message(user_id, call.message.message_id)
    render_settings_panel(user_id)

def process_teacher_fio_change(message):
    from bot.utils.api import api_update_user
    user_id = int(message.from_user.id)
    new_fio_raw = message.text.strip()
    new_fio = normalize_full_fio(new_fio_raw)

    if not is_valid_full_fio(new_fio):
        msg = bot.send_message(
            user_id,
            "❌ Неверный формат. Введите полностью: *Фамилия Имя Отчество*.\n"
            "Примеры: Иванов Иван Иванович, Сидорова Мария Петровна",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_teacher_fio_change)
        return

    api_update_user(user_id, {"teacher_fio": new_fio})
    bot.send_message(user_id, f"✅ ФИО успешно изменено на: *{new_fio}*", parse_mode='Markdown')

def process_teacher_task_file(message, group_name):
    user_id = message.from_user.id
    user = api_get_user(user_id) or {}
    teacher_fio = user.get("teacher_fio", "Неизвестно")

    if message.content_type not in ["document", "photo"]:
        msg = bot.send_message(user_id, "❌ Отправьте, пожалуйста, файл или фото.")
        bot.register_next_step_handler(msg, lambda m: process_teacher_task_file(m, group_name))
        return

    users = [u for u in api_get_users() if u.get("group_name") == group_name]
    count_sent = 0

    if message.content_type == "document":
        for u in users:
            try:
                bot.send_document(
                    u["user_id"],
                    message.document.file_id,
                    caption=f"📚 Новое задание от преподавателя *{teacher_fio}* для группы *{group_name}*",
                    parse_mode="Markdown"
                )
                count_sent += 1
            except Exception:
                pass
    elif message.content_type == "photo":
        photo_id = message.photo[-1].file_id
        for u in users:
            try:
                bot.send_photo(
                    u["user_id"],
                    photo_id,
                    caption=f"📚 Новое задание от преподавателя *{teacher_fio}* для группы *{group_name}*",
                    parse_mode="Markdown"
                )
                count_sent += 1
            except Exception:
                pass

    bot.send_message(
        user_id,
        f"✅ Задание успешно отправлено {count_sent} студентам группы *{group_name}*.",
        parse_mode="Markdown"
    )