from telebot import types
from bot.core import bot
from bot.handlers.commands import is_admin, is_teacher, render_settings_panel, send_group_selection
from bot.utils.api import api_update_user

@bot.callback_query_handler(func=lambda call: call.data in ("change_group", "enable_schedule", "disable_schedule", "change_time"))
def settings_callbacks(call):
    user_id = int(call.from_user.id)
    data = call.data

    if data == "change_group":
        send_group_selection(user_id)
        bot.answer_callback_query(call.id, "Выберите группу из списка ниже")
        return

    if data == "enable_schedule":
        api_update_user(user_id, {"schedule_enabled": True})
        bot.answer_callback_query(call.id, "🔔 Ежедневная рассылка включена")
        render_settings_panel(user_id)
        return

    if data == "disable_schedule":
        api_update_user(user_id, {"schedule_enabled": False})
        bot.answer_callback_query(call.id, "🔕 Ежедневная рассылка отключена")
        render_settings_panel(user_id)
        return

    if data == "change_time":
        msg = bot.send_message(user_id, "⏰ Введите время отправки в формате ЧЧ:ММ (например, 08:00):")
        from bot.handlers.text import process_change_time
        bot.register_next_step_handler(msg, process_change_time)
        return