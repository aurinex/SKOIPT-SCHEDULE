from telebot import types
from config import ADMINS
from bot.core import bot
from bot.keyboards import create_main_keyboard, group_selection_keyboard
from bot.messages import welcome_text, settings_text
from bot.utils.api import (
    api_get_user, api_update_user, api_create_user, api_get_schedule,
    api_get_teacher_schedule
)
from bot.utils.schedule_utils import (
    get_current_day, get_tomorrow_day, format_schedule_for_day, format_teacher_schedule_for_day
)
from bot.utils.fio_utils import fio_full_to_initials, normalize_full_fio, is_valid_full_fio

def is_admin(user_id: int) -> bool:
    u = api_get_user(user_id) or {}
    role = u.get('role', 'student')
    if user_id in ADMINS and role != 'admin':
        api_update_user(user_id, {"role": "admin"})
        role = 'admin'
    return role == 'admin'

def is_teacher(user_id: int) -> bool:
    u = api_get_user(user_id) or {}
    role = u.get('role', 'student')
    if user_id in ADMINS and role != 'admin':
        api_update_user(user_id, {"role": "admin"})
        role = 'admin'
    return role in ['teacher', 'admin']

def send_group_selection(user_id: int):
    kb = group_selection_keyboard(is_admin(user_id), is_teacher(user_id))
    bot.send_message(user_id, welcome_text(is_admin(user_id), is_teacher(user_id)), reply_markup=kb)

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = int(message.from_user.id)
    user = api_get_user(user_id)
    username = message.from_user.username or ""
    if user and user.get("username") != username:
        api_update_user(user_id, {"username": username})

    if not user:
        role = 'admin' if user_id in ADMINS else 'student'
        user = api_create_user(user_id, role=role, username=username)

    if not user:
        bot.send_message(user_id, "❌ Сервер недоступен. Попробуйте позже.")
        return

    if user_id in ADMINS and user.get('role') != 'admin':
        user = api_update_user(user_id, {"role": "admin"}) or user

    user_role = user.get('role', 'student')
    teacher_fio = user.get('teacher_fio')

    if user_role in ('teacher', 'admin') and not teacher_fio:
        msg = bot.send_message(
            user_id,
            "👨‍🏫 *Добро пожаловать, преподаватель!*\n\n"
            "Пожалуйста, введите ваше ФИО полностью (например: Иванов Иван Иванович):",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_teacher_name)
        return

    if user_role in ('teacher', 'admin') and teacher_fio:
        api_update_user(user_id, {"group_name": "Преподаватель"})
        keyboard = create_main_keyboard(user_id, is_teacher=True, is_admin=is_admin(user_id))
        bot.send_message(
            user_id,
            f"👨‍🏫 *Мы вас все еще помним, {teacher_fio}!*\n\n"
            f"Используйте кнопки ниже для работы с ботом:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    if not user.get('group_name'):
        send_group_selection(user_id)
        return

    keyboard = create_main_keyboard(user_id, is_teacher=False, is_admin=is_admin(user_id))
    bot.send_message(
        user_id,
        f"👋 Добро пожаловать в бот расписания Салаватского колледжа\n\n"
        f"📚 Ваша группа: {user.get('group_name')}\n\n"
        f"Используйте кнопки ниже для работы с ботом:",
        reply_markup=keyboard
    )

@bot.message_handler(commands=['feedback'])
def feedback_command(message):
    user_id = message.from_user.id
    msg = bot.send_message(
        user_id,
        "💬 Пожалуйста, опишите проблему или оставьте отзыв. "
        "Ваше сообщение будет отправлено администраторам.\n\n"
        "Для отмены — напишите «отмена»."
    )
    bot.register_next_step_handler(msg, process_feedback)
    

def process_feedback(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text.lower() in ("отмена", "cancel"):
        bot.send_message(user_id, "❌ Отправка отменена.")
        return

    # Формируем текст фидбека
    feedback_msg = (
        f"📩 <b>Новый фидбек от пользователя</b>\n\n"
        f"🧑‍💻 <b>ID:</b> {user_id}\n"
        f"👤 <b>Username:</b> @{message.from_user.username or 'нет'}\n\n"
        f"💬 <b>Сообщение:</b>\n{text}"
    )

    # Отправляем всем администраторам
    from config import ADMINS
    for admin_id in ADMINS:
        try:
            bot.send_message(admin_id, feedback_msg, parse_mode="HTML")
        except Exception:
            pass

    bot.send_message(user_id, "✅ Ваше сообщение успешно отправлено администраторам. Спасибо за отзыв!")

@bot.message_handler(commands=['schedule'])
def schedule_command(message):
    user_id = int(message.from_user.id)
    user = api_get_user(user_id) or {}

    if is_teacher(user_id):
        teacher_fio = user.get('teacher_fio')
        fio_key = fio_full_to_initials(teacher_fio or '')
        today = get_current_day()
        if not today:
            tomorrow = get_tomorrow_day()
            if tomorrow:
                sch = api_get_teacher_schedule(fio_key)
                text = format_teacher_schedule_for_day(teacher_fio or '', sch or {}, tomorrow)
                bot.send_message(user_id, f"📅 Сегодня воскресенье! Завтра ({tomorrow}):\n\n{text}")
            else:
                bot.send_message(user_id, "🎉 Сегодня воскресенье - выходной!")
        else:
            sch = api_get_teacher_schedule(fio_key)
            text = format_teacher_schedule_for_day(teacher_fio or '', sch or {}, today)
            bot.send_message(user_id, text)
        return

    group_name = user.get('group_name')
    if not group_name:
        bot.send_message(user_id, "❌ Сначала выберите вашу группу с помощью команды /start")
        return
    today = get_current_day()
    if not today:
        tomorrow = get_tomorrow_day()
        if tomorrow:
            sch = api_get_schedule(group_name)
            schedule_text = format_schedule_for_day(group_name, sch or {}, tomorrow)
            bot.send_message(user_id, f"📅 Сегодня воскресенье! Завтра ({tomorrow}):\n\n{schedule_text}")
        else:
            bot.send_message(user_id, "🎉 Сегодня воскресенье - выходной!")
    else:
        sch = api_get_schedule(group_name)
        schedule_text = format_schedule_for_day(group_name, sch or {}, today)
        bot.send_message(user_id, schedule_text, protect_content=True)

@bot.message_handler(commands=['settings'])
def settings_command(message):
    render_settings_panel(message.from_user.id)

def process_teacher_name(message):
    from bot.utils.api import api_update_user
    teacher_fio_raw = message.text.strip()
    teacher_fio = normalize_full_fio(teacher_fio_raw)

    if not is_valid_full_fio(teacher_fio):
        msg = bot.send_message(
            message.from_user.id,
            "❌ Неверный формат ФИО. Пожалуйста, введите полностью: *Фамилия Имя Отчество*.\n"
            "Примеры: Иванов Иван Иванович, Сидорова Мария Петровна, Петров-Иванов Алексей Сергеевич",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_teacher_name)
        return

    api_update_user(message.from_user.id, {"teacher_fio": teacher_fio, "group_name": "Преподаватель"})

    keyboard = create_main_keyboard(message.from_user.id, is_teacher=True, is_admin=is_admin(message.from_user.id))
    bot.send_message(
        message.from_user.id,
        f"✅ *{teacher_fio}*, мы вас запомнили!\n\n"
        f"Теперь вы можете:\n"
        f"• Использовать панель преподавателя\n"
        f"• Просматривать расписание групп\n"
        f"• Настроить ежедневную рассылку\n\n"
        f"Используйте кнопки ниже или команды:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def render_settings_panel(user_id: int):
    from bot.utils.api import api_get_user
    user = api_get_user(user_id) or {}
    user_role = user.get('role', 'student')

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 Сменить группу", callback_data="change_group"))

    enabled = bool(user.get('schedule_enabled', False))
    sched_time = user.get('schedule_time', '08:00')
    if enabled:
        kb.add(types.InlineKeyboardButton("🔕 Отключить ежедневное расписание", callback_data="disable_schedule"))
    else:
        kb.add(types.InlineKeyboardButton("🔔 Включить ежедневное расписание", callback_data="enable_schedule"))
    kb.add(types.InlineKeyboardButton("⏰ Изменить время отправки", callback_data="change_time"))

    if is_teacher(user_id):
        kb.add(types.InlineKeyboardButton("👨‍🏫 Настройки преподавателя", callback_data="teacher_settings"))

    current_group = user.get('group_name') or "не выбрана"
    teacher_fio = user.get('teacher_fio') if is_teacher(user_id) else None
    text = settings_text(user_role, current_group, enabled, sched_time, teacher_fio)

    bot.send_message(user_id, text, reply_markup=kb)