from telebot import types
from config import ROLES
from .utils.api import api_get_all_groups
from .utils.schedule_utils import get_current_day
from .utils.fio_utils import fio_full_to_initials
from .utils.api import api_get_teacher_schedule

def create_main_keyboard(user_id: int, is_teacher: bool, is_admin: bool) -> types.ReplyKeyboardMarkup:
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    keyboard.add(types.KeyboardButton("📅 Сегодня"), types.KeyboardButton("⚙️ Настройки"))
    keyboard.add(types.KeyboardButton("📅 ПН"), types.KeyboardButton("📅 ВТ"), types.KeyboardButton("📅 СР"))
    keyboard.add(types.KeyboardButton("📅 ЧТ"), types.KeyboardButton("📅 ПТ"), types.KeyboardButton("📅 СБ"))
    if is_teacher:
        keyboard.add(types.KeyboardButton("👨‍🏫 Панель преподавателя"))
    if is_admin:
        keyboard.add(types.KeyboardButton("👑 Админ панель"))
    return keyboard

def group_selection_keyboard(is_admin: bool) -> types.ReplyKeyboardMarkup:
    groups = api_get_all_groups()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if is_admin:
        keyboard.add(types.KeyboardButton("⏩ Пропустить"))
    for i in range(0, len(groups), 2):
        row = groups[i:i+2]
        keyboard.add(*[types.KeyboardButton(group) for group in row])
    keyboard.add(types.KeyboardButton("❌ Отмена"))
    return keyboard