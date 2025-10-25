from telebot import types
from bot.core import bot
from bot.handlers.commands import is_teacher, is_admin, render_settings_panel
from bot.utils.api import (
    api_get_user, api_get_users, api_update_user, api_get_schedule, api_upload_schedule, api_get_all_groups, api_get_teacher_schedule
)
from bot.utils.schedule_utils import (
    get_current_day, get_tomorrow_day, format_schedule_for_day, format_teacher_schedule_for_day
)
from bot.utils.fio_utils import fio_full_to_initials
from bot.keyboards import create_main_keyboard

pending_uploads = {}  # user_id → {"docx": bytes, "json": bytes}

@bot.message_handler(func=lambda message: True, content_types=['text', 'document'])
def text_message_handler(message):
    user_id = int(message.from_user.id)

    if message.content_type == 'document':
        user = api_get_user(user_id) or {}
        if user.get('role') != 'admin':
            bot.send_message(user_id, "❌ У вас нет прав для загрузки файлов.")
            return
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        fname = (message.document.file_name or '').lower()

        if user_id not in pending_uploads:
            pending_uploads[user_id] = {}

        if fname.endswith('.json'):
            try:
                import json
                json.loads(file_bytes.decode('utf-8'))
                pending_uploads[user_id]['json'] = file_bytes
                if 'docx' in pending_uploads[user_id]:
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    markup.add(types.KeyboardButton("📤 Загрузить оба файла"))
                    markup.add(types.KeyboardButton("❌ Отмена"))
                    bot.send_message(
                        user_id,
                        "📂 Оба файла получены!\nНажмите «📤 Загрузить оба файла», чтобы отправить их на сервер.",
                        reply_markup=markup
                    )
                else:
                    bot.send_message(user_id, "✅ JSON получен. Теперь отправьте DOCX.")
            except Exception:
                bot.send_message(user_id, "❌ JSON повреждён или неверный формат.")
            return

        elif fname.endswith('.docx'):
            pending_uploads[user_id]['docx'] = file_bytes
            if 'json' in pending_uploads[user_id]:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("📤 Загрузить оба файла"))
                markup.add(types.KeyboardButton("❌ Отмена"))
                bot.send_message(
                    user_id,
                    "📂 Оба файла получены!\nНажмите «📤 Загрузить оба файла», чтобы отправить их на сервер.",
                    reply_markup=markup
                )
            else:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("📤 Загрузить расписание"))
                markup.add(types.KeyboardButton("❌ Отмена"))
                bot.send_message(
                    user_id,
                    "✅ DOCX получен.\n"
                    "(Необязательно) Отправьте JSON со сменами, "
                    "или нажмите «📤 Загрузить расписание», чтобы отправить только DOCX.",
                    reply_markup=markup
                )
            return

        data = pending_uploads[user_id]
        if 'docx' in data and 'json' in data:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("📤 Загрузить оба файла"))
            markup.add(types.KeyboardButton("❌ Отмена"))
            bot.send_message(
                user_id,
                "📂 Оба файла получены!\nНажмите «📤 Загрузить оба файла», чтобы отправить их на сервер.",
                reply_markup=markup
            )
        return

    text = (message.text or '').strip()

    if text == "⏩ Пропустить" and is_admin(user_id):
        api_update_user(user_id, {"group_name": "Админ"})
        keyboard = create_main_keyboard(user_id, is_teacher=is_teacher(user_id), is_admin=is_admin(user_id))
        bot.send_message(
            user_id,
            "✅ Регистрация завершена!\n"
            "👑 Вы зарегистрированы как администратор\n\n"
            "Теперь вы можете использовать все функции бота:",
            reply_markup=keyboard
        )
        return

    if text in set(api_get_all_groups()):
        if is_teacher(user_id):
            group_name = text
            sch = api_get_schedule(group_name)
            schedule_text = format_schedule_for_day(group_name, sch or {}, get_current_day() or "Понедельник")
            bot.send_message(user_id, schedule_text)
            return
        api_update_user(user_id, {'role': 'student', 'group_name': text})
        keyboard = create_main_keyboard(user_id, is_teacher=False, is_admin=is_admin(user_id))
        bot.send_message(
            user_id,
            f"✅ Группа {text} установлена!\n"
            f"Теперь вы можете:\n"
            f"• Получить расписание на любой день недели\n"
            f"• Использовать кнопку 'Сегодня' для быстрого доступа\n"
            f"• Настроить ежедневную рассылку\n\n"
            f"Используйте кнопки ниже или команды:\n"
            f"/schedule - расписание на сегодня\n"
            f"/tomorrow - расписание на завтра\n"
            f"/settings - настройки",
            reply_markup=keyboard
        )
        return

    if text == "👑 Админ панель" and is_admin(user_id):
        from bot.handlers.admin import admin_command
        admin_command(message)
        return
    if text == "👨‍🏫 Панель преподавателя" and is_teacher(user_id):
        from bot.handlers.teachers import teacher_command
        teacher_command(message)
        return

    if text == "📅 Сегодня":
        if is_teacher(user_id):
            teacher_fio = (api_get_user(user_id) or {}).get('teacher_fio')
            today = get_current_day()
            fio_key = fio_full_to_initials(teacher_fio or '')
            if not today:
                tomorrow = get_tomorrow_day()
                if tomorrow:
                    sch = api_get_schedule((api_get_user(user_id) or {}).get('group_name',''))
                    t = format_teacher_schedule_for_day(teacher_fio or '', api_get_teacher_schedule(fio_key) or {}, tomorrow)
                    bot.send_message(user_id, f"📅 Сегодня воскресенье! Завтра ({tomorrow}):\n\n{t}")
                else:
                    bot.send_message(user_id, "🎉 Сегодня воскресенье - выходной!")
            else:
                sch = api_get_teacher_schedule(fio_key)
                t = format_teacher_schedule_for_day(teacher_fio or '', sch or {}, today)
                bot.send_message(user_id, t)
            return
        group_name = (api_get_user(user_id) or {}).get('group_name')
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
        return

    if text == "⚙️ Настройки":
        render_settings_panel(message.from_user.id)
        return

    if text in ["📅 ПН", "📅 ВТ", "📅 СР", "📅 ЧТ", "📅 ПТ", "📅 СБ"]:
        day_map = {
            "📅 ПН": "Понедельник",
            "📅 ВТ": "Вторник",
            "📅 СР": "Среда",
            "📅 ЧТ": "Четверг",
            "📅 ПТ": "Пятница",
            "📅 СБ": "Суббота"
        }
        day = day_map[text]
        if is_teacher(user_id):
            teacher_fio = (api_get_user(user_id) or {}).get('teacher_fio')
            fio_key = fio_full_to_initials(teacher_fio or '')
            sch = api_get_teacher_schedule(fio_key)
            t = format_teacher_schedule_for_day(teacher_fio or '', sch or {}, day)
            bot.send_message(user_id, t)
            return
        group_name = (api_get_user(user_id) or {}).get('group_name')
        if not group_name:
            bot.send_message(user_id, "❌ Сначала выберите вашу группу с помощью команды /start")
            return
        sch = api_get_schedule(group_name)
        schedule_text = format_schedule_for_day(group_name, sch or {}, day)
        bot.send_message(user_id, schedule_text, protect_content=True)
        return

    if text == "❌ Отмена":
        pending_uploads.pop(user_id, None)
        group_name = (api_get_user(user_id) or {}).get('group_name')
        if group_name:
            keyboard = create_main_keyboard(user_id, is_teacher=is_teacher(user_id), is_admin=is_admin(user_id))
            bot.send_message(user_id, "Действие отменено.", reply_markup=keyboard)
        else:
            bot.send_message(user_id, "Действие отменено. Используйте /start для выбора группы.")
        return
    
    if text == "📤 Загрузить расписание":
        data = pending_uploads.get(user_id)
        if not data or 'docx' not in data:
            bot.send_message(user_id, "❌ Сначала отправьте DOCX-файл.")
            return

        bot.send_message(user_id, "⏳ Отправка расписания на сервер...")

        resp = api_upload_schedule(data['docx'], None)
        pending_uploads.pop(user_id, None)

        keyboard = create_main_keyboard(user_id, is_teacher=is_teacher(user_id), is_admin=is_admin(user_id))

        if resp is not None:
            bot.send_message(user_id, "✅ Расписание успешно обновлено!", reply_markup=keyboard)
            users = api_get_users()
            for u in users:
                try:
                    bot.send_message(u["user_id"], "📢 Расписание обновлено! Проверьте своё расписание в боте.")
                except Exception:
                    pass
        else:
            bot.send_message(user_id, "❌ Ошибка при загрузке расписания.", reply_markup=keyboard)
        return
    
    if text == "📤 Загрузить оба файла":
        data = pending_uploads.get(user_id)
        if not data or 'docx' not in data:
            bot.send_message(user_id, "❌ Сначала отправьте DOCX и JSON файлы.")
            return

        bot.send_message(user_id, "⏳ Отправка файлов на сервер...")

        resp = api_upload_schedule(data['docx'], data.get('json'))
        pending_uploads.pop(user_id, None)

        keyboard = create_main_keyboard(user_id, is_teacher=is_teacher(user_id), is_admin=is_admin(user_id))

        if resp is not None:
            bot.send_message(user_id, "✅ Расписание успешно обновлено!", reply_markup=keyboard)
            users = api_get_users()
            for u in users:
                uid = u.get("user_id")
                try:
                    bot.send_message(uid, "📢 Расписание обновлено! Проверьте своё расписание.")
                except Exception:
                    pass
        else:
            bot.send_message(user_id, "❌ Ошибка при загрузке расписания.", reply_markup=keyboard)
        return

    bot.send_message(
        user_id,
        "❌ Неизвестная команда. Используйте кнопки или команды:\n"
        "/start - начать работу\n"
        "/schedule - расписание на сегодня\n"
        "/settings - настройки"
    )

def process_change_time(message):
    user_id = int(message.from_user.id)
    text = message.text.strip()
    import re
    if not re.match(r'^\d{2}:\d{2}$', text):
        msg = bot.send_message(user_id, "❌ Неверный формат. Введите время как ЧЧ:ММ, например 08:00.")
        bot.register_next_step_handler(msg, process_change_time)
        return
    hh, mm = text.split(':')
    try:
        hh_i, mm_i = int(hh), int(mm)
        if not (0 <= hh_i < 24 and 0 <= mm_i < 60):
            raise ValueError
    except:
        msg = bot.send_message(user_id, "❌ Неверное время. Введите ЧЧ:ММ, например 08:00.")
        bot.register_next_step_handler(msg, process_change_time)
        return
    api_update_user(user_id, {"schedule_time": text})
    bot.send_message(user_id, f"✅ Время ежедневной отправки установлено: {text}")
    render_settings_panel(user_id)