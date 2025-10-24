import os
import re
import io
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
import requests, json
from requests.adapters import HTTPAdapter, Retry
import telebot
from telebot import types
import traceback

pending_uploads = {}  # user_id → {"docx": bytes, "json": bytes}

def log_error(context: str, e: Exception):
    """Выводит понятный лог об ошибке с указанием контекста"""
    print(f"\n[❌ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ошибка в {context}:")
    print(f"Тип: {type(e).__name__}")
    print(f"Описание: {e}")
    tb = traceback.format_exc(limit=2)
    print(f"Трассировка: {tb}\n")

#8253140899:AAFPdH80KTgoKRAUTyuqBJhrs_DLIkw9zto 172.17.0.1

# ============================ КОНФИГ ============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "8253140899:AAFPdH80KTgoKRAUTyuqBJhrs_DLIkw9zto")
API_URL = os.getenv("API_URL", "http://172.17.0.1:3020")

# Роли пользователей
ROLES = {
    'student': '👨‍🎓 Студент',
    'teacher': '👨‍🏫 Преподаватель',
    'admin':   '👑 Администратор'
}

# Администраторы (user_id)
ADMINS = [1044229010, 965614231]

# Дни недели
days_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# ============================ HTTP СЕССИЯ ============================
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))

def _get(url, **kwargs):
    return session.get(url, timeout=15, **kwargs)

def _post(url, **kwargs):
    return session.post(url, timeout=30, **kwargs)

def _put(url, **kwargs):
    return session.put(url, timeout=30, **kwargs)

# ============================ API ============================

def api_get_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/users/{user_id}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users/{user_id} → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log_error(f"api_get_user({user_id})", e)
        return None

def api_create_user(user_id: int, role: str = "student", username: str = "") -> Optional[Dict[str, Any]]:
    payload = {"user_id": user_id, "role": role, "username": username}
    try:
        r = _post(f"{API_URL}/users/", json=payload)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] POST /users → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log_error(f"api_create_user({user_id})", e)
        return None

def api_update_user(user_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        r = _put(f"{API_URL}/users/{user_id}", json=data)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] PUT /users/{user_id} → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log_error(f"api_update_user({user_id})", e)
        return None

def api_get_users() -> List[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/users/")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users → {r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        log_error("api_get_users()", e)
        return []
    
                                                # === API: users с пагинацией ===
def api_get_users_page(skip: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/users/", params={"skip": skip, "limit": limit})
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users?skip={skip}&limit={limit} → {r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        log_error(f"api_get_users_page(skip={skip}, limit={limit})", e)
        return []

                                                # «подглядываем» на 1 запись вперёд, чтобы понять есть ли следующая страница
def api_get_users_page_peek(skip: int = 0, limit: int = 10) -> tuple[List[Dict[str, Any]], bool]:
    rows = api_get_users_page(skip=skip, limit=limit + 1)
    has_next = len(rows) > limit
    return rows[:limit], has_next

def api_get_all_groups() -> List[str]:
    try:
        r = _get(f"{API_URL}/schedule/")
        if r.status_code != 200:
            return []
        arr = r.json()
        groups: List[str] = []
        for item in arr:
            if isinstance(item, dict) and "group_name" in item:
                groups.append(item["group_name"])
            elif isinstance(item, str):
                groups.append(item)
        # сортировка как в старой версии
        def key_fn(g: str):
            m = re.match(r"(\d+)", g)
            course = int(m.group(1)) if m else 0
            m2 = re.match(r"\d+\s*([А-Яа-яA-Za-z]*)", g)
            suf = m2.group(1) if m2 else g
            return (course, suf)
        return sorted(list(dict.fromkeys(groups)), key=key_fn)
    except:
        return []

def api_get_schedule(group_name: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/schedule/{group_name}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /schedule/{group_name} → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log_error(f"api_get_schedule({group_name})", e)
        return None
    
def api_get_teacher_schedule(fio_key: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/schedule/teacher/{fio_key}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /schedule/teacher/{fio_key} → {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        log_error(f"api_get_schedule({fio_key})", e)
        return None

def api_upload_schedule(docx_bytes: bytes, json_bytes: bytes | None = None):
    files = {
        "schedule_file": ("schedule.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }
    if json_bytes:
        files["shifts_file"] = ("group_shifts.json", json_bytes, "application/json")

    try:
        resp = _post(f"{API_URL}/schedule/upload", files=files)
        if resp.status_code == 200:
            return resp.json()
        else:
            print("Ошибка:", resp.text)
            return None
    except Exception as e:
        print("Ошибка запроса:", e)
        return None
    
def check_api_connection():
    try:
        print(f"🔍 Проверка API-доступности: {API_URL}")
        r = _get(f"{API_URL}/users/")
        if r.status_code == 200:
            print("✅ API доступно, соединение установлено!")
        else:
            print(f"⚠️ API ответило с кодом {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log_error("check_api_connection()", e)
        print("❌ Не удалось подключиться к API. Проверь URL и сервер.")

# ====================== ФИО: валидация и нормализация ======================
FIO_FULL_RE = re.compile(
    r'^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?$'
)

def _cap(part: str) -> str:
    return "-".join(s[:1].upper() + s[1:].lower() for s in part.split("-"))

def normalize_full_fio(text: str) -> str:
    text = re.sub(r'\s+', ' ', text.strip())
    parts = text.split(" ")
    if len(parts) != 3:
        return text
    return " ".join(_cap(p) for p in parts)

def is_valid_full_fio(text: str) -> bool:
    text = re.sub(r'\s+', ' ', text.strip())
    return bool(FIO_FULL_RE.match(text))

def fio_full_to_initials(full_fio: str) -> str:
    def init(n: str) -> str:
        return (n[:1].upper() + ".") if n else ""
    parts = re.sub(r'\s+', ' ', full_fio.strip()).split(' ')
    if len(parts) < 2:
        return full_fio.strip()
    fam = parts[0]
    name = parts[1] if len(parts) > 1 else ""
    otch = parts[2] if len(parts) > 2 else ""
    fam = "-".join(s[:1].upper() + s[1:].lower() for s in fam.split("-"))
    return f"{fam} {init(name)}{init(otch)}"

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

def get_user_role(user_id: int) -> str:
    user = api_get_user(user_id)
    role = (user or {}).get('role', 'student')
    # Понижаем/повышаем роль локально, если в ADMINS
    if user_id in ADMINS and role != 'admin':
        api_update_user(user_id, {"role": "admin"})
        role = 'admin'
    return role

def is_admin(user_id: int) -> bool:
    return get_user_role(user_id) == 'admin'

def is_teacher(user_id: int) -> bool:
    return get_user_role(user_id) in ['teacher', 'admin']

# ====================== ФОРМАТИРОВАНИЕ РАСПИСАНИЯ ======================

def format_schedule_for_day(group_name: str, schedule_doc: Dict[str, Any], day: str) -> str:
    if not schedule_doc:
        return "❌ Расписание для вашей группы не найдено"
    schedule = schedule_doc.get('schedule', {})
    zero_lesson = (schedule.get('zero_lesson') or {}).get(day, {})
    day_lessons = (schedule.get('days') or {}).get(day, {})
    if not zero_lesson and not day_lessons:
        return f"📅 В {day} пар нет"
    result = f"📚 Расписание на {day} ({group_name}):\n\n"
    lessons_today: List[str] = []
    if zero_lesson:
        subject = zero_lesson.get('subject', '')
        classroom = zero_lesson.get('classroom', '')
        teacher = zero_lesson.get('teacher', '')
        if subject:
            lesson_text = f"0. {subject}"
            if classroom:
                lesson_text += f" {classroom} каб."
            if teacher:
                lesson_text += f" ({teacher})"
            lessons_today.append(lesson_text)
    for lesson_num, lesson_info in sorted((day_lessons or {}).items(), key=lambda x: int(x[0])):
        subject = lesson_info.get('subject', '')
        classroom = lesson_info.get('classroom', '')
        teacher = lesson_info.get('teacher', '')
        if subject:
            lesson_text = f"{lesson_num}. {subject}"
            if classroom:
                lesson_text += f" {classroom} каб."
            if teacher:
                lesson_text += f" ({teacher})"
            lessons_today.append(lesson_text)
    if not lessons_today:
        return f"📅 В {day} пар нет"
    result += "\n".join(lessons_today)
    return result


def format_teacher_schedule_for_day(teacher_full_fio: str, schedule_doc: Dict[str, Any], day: str) -> str:
    if not teacher_full_fio:
        return "❌ Не указано ФИО преподавателя"
    if not schedule_doc or 'schedule' not in schedule_doc:
        return f"📭 Расписание для {teacher_full_fio} не найдено"

    schedule = schedule_doc.get('schedule', {})
    first_shift = []
    second_shift = []

    for shift_name, shift_dict in schedule.items():
        day_dict = shift_dict.get(day, {})
        for num, info in sorted(day_dict.items(), key=lambda x: int(x[0])):
            subject = info.get('subject', '')
            group = info.get('group', '')
            room = info.get('classroom', '')
            line = f"• {num}. {subject}"
            if group:
                line += f" — {group}"
            if room:
                line += f" ({room})"
            if shift_name == 'first_shift':
                first_shift.append(line)
            else:
                second_shift.append(line)

    if not first_shift and not second_shift:
        return f"📅 В {day} пар нет"

    parts = [f"👨‍🏫 Расписание преподавателя на {day}\n{teacher_full_fio}"]
    if first_shift:
        parts.append("1 Смена:\n" + "\n".join(first_shift))
    if second_shift:
        parts.append("2 Смена:\n" + "\n".join(second_shift))

    return "\n\n".join(parts)

# ====================== ДНИ НЕДЕЛИ ======================

def get_current_day() -> Optional[str]:
    today = datetime.now().weekday()
    if today == 6:
        return None
    return days_ru[today]

def get_tomorrow_day() -> Optional[str]:
    tomorrow = (datetime.now() + timedelta(days=1)).weekday()
    if tomorrow == 6:
        return None
    return days_ru[tomorrow]

# ====================== КЛАВИАТУРЫ ======================

def create_main_keyboard(user_id: int) -> types.ReplyKeyboardMarkup:
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    keyboard.add(types.KeyboardButton("📅 Сегодня"), types.KeyboardButton("⚙️ Настройки"))
    keyboard.add(types.KeyboardButton("📅 ПН"), types.KeyboardButton("📅 ВТ"), types.KeyboardButton("📅 СР"))
    keyboard.add(types.KeyboardButton("📅 ЧТ"), types.KeyboardButton("📅 ПТ"), types.KeyboardButton("📅 СБ"))
    if is_teacher(user_id):
        keyboard.add(types.KeyboardButton("👨‍🏫 Панель преподавателя"))
    if is_admin(user_id):
        keyboard.add(types.KeyboardButton("👑 Админ панель"))
    return keyboard

# ====================== РЕНДЕР ЭКРАНОВ ======================

def send_group_selection(user_id: int):
    groups = api_get_all_groups()
    if not groups:
        bot.send_message(user_id, "❌ Расписание временно недоступно. Попробуйте позже.")
        return
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Если администратор — добавляем "Пропустить"
    if is_admin(user_id):
        keyboard.add(types.KeyboardButton("⏩ Пропустить"))
    for i in range(0, len(groups), 2):
        row = groups[i:i+2]
        keyboard.add(*[types.KeyboardButton(group) for group in row])
    keyboard.add(types.KeyboardButton("❌ Отмена"))

    welcome_text = "👋 Добро пожаловать в бот расписания Салаватского колледжа\n\n"
    if is_admin(user_id):
        welcome_text += "Вы можете выбрать группу или нажать 'Пропустить'\n\n"
    elif is_teacher(user_id):
        welcome_text += "Выберите группу для просмотра расписания:\n\n"
    else:
        welcome_text += "📚 Выберите вашу группу из списка ниже:"

    bot.send_message(user_id, welcome_text, reply_markup=keyboard)


def render_settings_panel(user_id: int, message_id: Optional[int] = None):
    user = api_get_user(user_id) or {}
    user_role = user.get('role', 'student')
    # Собираем клавиатуру
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔄 Сменить группу", callback_data="change_group"))

    enabled = bool(user.get('schedule_enabled', False))
    sched_time = user.get('schedule_time', '08:00')
    if enabled:
        keyboard.add(types.InlineKeyboardButton("🔕 Отключить ежедневное расписание", callback_data="disable_schedule"))
    else:
        keyboard.add(types.InlineKeyboardButton("🔔 Включить ежедневное расписание", callback_data="enable_schedule"))
    keyboard.add(types.InlineKeyboardButton("⏰ Изменить время отправки", callback_data="change_time"))

    if is_teacher(user_id):
        keyboard.add(types.InlineKeyboardButton("👨‍🏫 Настройки преподавателя", callback_data="teacher_settings"))

    # Текст
    current_group = user.get('group_name') or "не выбрана"
    schedule_status = "включена" if enabled else "отключена"
    teacher_info = ""
    teacher_fio = user.get('teacher_fio')
    if is_teacher(user_id) and teacher_fio:
        teacher_info = f"👨‍🏫 ФИО: {teacher_fio}\n"

    text = (
        f"⚙️ Настройки | {ROLES.get(user_role, user_role)}\n\n"
        f"{teacher_info}"
        f"📚 Текущая группа: {current_group}\n"
        f"🔔 Ежедневная рассылка: {schedule_status}\n"
        f"⏰ Время отправки: {sched_time}"
    )

    if message_id is not None:
        bot.edit_message_text(text, user_id, message_id, reply_markup=keyboard)
    else:
        bot.send_message(user_id, text, reply_markup=keyboard)


def render_admin_panel(chat_id: int, message_id: Optional[int] = None):
    text = "👑 Панель администратора\n\nВыберите действие:"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users"))
    kb.add(types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.add(types.InlineKeyboardButton("🔄 Обновить расписание", callback_data="admin_refresh"))
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


def render_teacher_panel(user_id: int, message_id: Optional[int] = None):
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

# ======================== ХЭНДЛЕРЫ КОМАНД ========================

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = int(message.from_user.id)
    user = api_get_user(user_id)
    username = message.from_user.username or ""
    if user and user.get("username") != username:
        api_update_user(user_id, {"username": username})

    # создаём пользователя при первом запуске
    if not user:
        # авто-роль admin из списка ADMINS
        role = 'admin' if user_id in ADMINS else 'student'
        username = message.from_user.username or ""
        user = api_create_user(user_id, role=role, username=username)

    if not user:
        bot.send_message(user_id, "❌ Сервер недоступен. Попробуйте позже.")
        return

    # Синхронизируем роль админа при первом старте
    if user_id in ADMINS and user.get('role') != 'admin':
        user = api_update_user(user_id, {"role": "admin"}) or user

    user_role = user.get('role', 'student')
    teacher_fio = user.get('teacher_fio')

    # Если преподаватель (или админ) и ФИО еще нет — запросить ФИО
    if user_role in ('teacher', 'admin') and not teacher_fio:
        msg = bot.send_message(
            user_id,
            "👨‍🏫 *Добро пожаловать, преподаватель!*\n\n"
            "Пожалуйста, введите ваше ФИО полностью (например: Иванов Иван Иванович):",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_teacher_name)
        return

    # Если преподаватель и ФИО уже есть — показать главное меню
    if user_role in ('teacher', 'admin') and teacher_fio:
        api_update_user(user_id, {"group_name": "Преподаватель"})
        keyboard = create_main_keyboard(user_id)
        bot.send_message(
            user_id,
            f"👨‍🏫 *Мы вас все еще помним, {teacher_fio}!*\n\n"
            f"Используйте кнопки ниже для работы с ботом:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return

    # Иначе — студент/непрепод: выбор группы (если не выбрана)
    if not user.get('group_name'):
        send_group_selection(user_id)
        return

    # Если группа уже выбрана — просто показать главное меню
    keyboard = create_main_keyboard(user_id)
    bot.send_message(
        user_id,
        f"👋 Добро пожаловать в бот расписания Салаватского колледжа\n\n"
        f"📚 Ваша группа: {user.get('group_name')}\n\n"
        f"Используйте кнопки ниже для работы с ботом:",
        reply_markup=keyboard
    )

@bot.message_handler(commands=['schedule'])
def schedule_command(message):
    user_id = int(message.from_user.id)
    user = api_get_user(user_id) or {}

    if is_teacher(user_id):
        teacher_fio = user.get('teacher_fio')
        # ключ для API: используем инициалы (Фамилия И.О.)
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

    # студент/обычный — как было
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
        bot.send_message(user_id, schedule_text)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = int(message.from_user.id)
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ У вас нет прав для доступа к этой команде.")
        return
    render_admin_panel(user_id)

@bot.message_handler(commands=['teacher'])
def teacher_command(message):
    user_id = int(message.from_user.id)
    if not is_teacher(user_id):
        bot.send_message(user_id, "❌ У вас нет прав для доступа к этой команде.")
        return
    render_teacher_panel(user_id)

@bot.message_handler(commands=['settings'])
def settings_command(message):
    render_settings_panel(message.from_user.id)

# ================== CALLBACK'и АДМИНА И ПРЕПОДА ==================

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callback_handler(call):
    user_id = call.from_user.id
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return
    
    # --- Управление пользователями с пагинацией ---
    if call.data.startswith("admin_users"):
        # ответим сразу, чтобы не словить "query is too old"
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
        # Виртуальный рефреш: предложить загрузить DOCX
        bot.answer_callback_query(call.id, "Загрузите DOCX-файл расписания сообщением — я отправлю его на сервер")
        bot.send_message(user_id, "📤 Отправьте DOCX-файл расписания.\n(Необязательно) Следом отправьте JSON со сменами `group_shifts.json`. Я загружу оба файла на сервер.")
    elif call.data == "admin_panel":
        render_admin_panel(user_id)  # открыть новой записью
        bot.answer_callback_query(call.id)
    elif call.data == "admin_set_teacher":
        set_teacher_callback(call)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_back":
        render_admin_panel(user_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('teacher_'))
def teacher_callback_handler(call):
    user_id = call.from_user.id
    if not is_teacher(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав для этого действия")
        return

    # === Мои занятия ===
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

        # Получаем расписание преподавателя
        sch = api_get_teacher_schedule(fio_key) or {}
        schedule = sch.get("schedule", {})

        # Собираем группы из обеих смен на сегодняшний день
        groups = set()
        for shift_name, shift_data in schedule.items():
            day_lessons = shift_data.get(today, {})
            for num, info in day_lessons.items():
                group = info.get("group")
                if group:
                    groups.add(group)

        # Создаём клавиатуру с кнопками групп
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

    # === Мои группы ===
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

    # === Настройки преподавателя ===
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

    # === Назад в панель преподавателя ===
    elif call.data == "teacher_back":
        render_teacher_panel(user_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    # === Отправка задания ===
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

# ============== CALLBACK'и НАСТРОЕК РАССЫЛКИ/ГРУППЫ ==============

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
        settings_command(call.message)
        return

    if data == "disable_schedule":
        api_update_user(user_id, {"schedule_enabled": False})
        bot.answer_callback_query(call.id, "🔕 Ежедневная рассылка отключена")
        settings_command(call.message)
        return

    if data == "change_time":
        msg = bot.send_message(user_id, "⏰ Введите время отправки в формате ЧЧ:ММ (например, 08:00):")
        bot.register_next_step_handler(msg, process_change_time)
        return

# ================== ВСПОМОГАТЕЛЬНЫЕ ЭКРАНЫ (АДМИН/ПРЕПОД) ==================

def build_admin_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users"))
    kb.add(types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.add(types.InlineKeyboardButton("🔄 Обновить расписание", callback_data="admin_refresh"))
    return kb

def show_user_management(call, skip: int = 0, limit: int = 10):
    user_id = call.from_user.id
    message_id = call.message.message_id

    skip = max(0, int(skip))
    limit = max(1, int(limit))

    rows, has_next = api_get_users_page_peek(skip=skip, limit=limit)
    if not rows and skip > 0:
        skip = max(0, skip - limit)
        rows, has_next = api_get_users_page_peek(skip=skip, limit=limit)

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

# def show_user_management(call):
#     user_id = call.from_user.id
#     message_id = call.message.message_id

#     rows = list(reversed(api_get_users()))[:10]  # последние по id
#     users_info = []
#     for u in rows:
#         uid = u.get('user_id')
#         uname = u.get('username')
#         role = u.get('role', 'student')
#         grp = u.get('group_name') or 'нет группы'
#         info = f"@{uname}, {uid}: {ROLES.get(role, role)}, группа: {grp}"
#         fio = u.get('teacher_fio')
#         if fio:
#             info += f", ФИО: {fio}"
#         users_info.append(info)

#     users_text = "\n".join(users_info) if users_info else "—"
#     keyboard = types.InlineKeyboardMarkup()
#     keyboard.add(types.InlineKeyboardButton("🎯 Назначить преподавателя", callback_data="admin_set_teacher"))
#     keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))

#     total = len(api_get_users())
#     bot.edit_message_text(
#         f"👥 Управление пользователями\n\n"
#         f"Всего пользователей: {total}!\n"
#         f"Последние пользователи:\n{users_text}",
#         user_id, message_id, reply_markup=keyboard
#     )

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


def show_teacher_settings(call):
    user_id = call.from_user.id
    message_id = call.message.message_id
    teacher_fio = (api_get_user(user_id) or {}).get('teacher_fio') or "Не указано"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✏️ Изменить ФИО", callback_data="teacher_change_fio"))
    keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="settings_back"))
    bot.edit_message_text(
        f"👨‍🏫 Настройки преподавателя\n\n"
        f"Текущее ФИО: {teacher_fio}",
        user_id, message_id, reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "settings_back")
def settings_back_handler(call):
    user_id = call.from_user.id
    render_settings_panel(user_id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

# =========== Назначение преподавателей (виртуально через /users) ===========

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
    text = message.text.strip()

    if not is_admin(admin_id):
        bot.send_message(admin_id, "❌ У вас нет прав для этого действия")
        return

    if text.lower() in ("отмена", "cancel", "назад"):
        bot.send_message(admin_id, "⛔️ Назначение отменено.")
        render_admin_panel(admin_id)
        return

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

# ================== ПРОЦЕССИНГ ИЗМЕНЕНИЙ ФИО ==================

def process_teacher_name(message):
    user_id = int(message.from_user.id)
    teacher_fio_raw = message.text.strip()
    teacher_fio = normalize_full_fio(teacher_fio_raw)

    if not is_valid_full_fio(teacher_fio):
        msg = bot.send_message(
            user_id,
            "❌ Неверный формат ФИО. Пожалуйста, введите полностью: *Фамилия Имя Отчество*.\n"
            "Примеры: Иванов Иван Иванович, Сидорова Мария Петровна, Петров-Иванов Алексей Сергеевич",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_teacher_name)
        return

    api_update_user(user_id, {"teacher_fio": teacher_fio, "group_name": "Преподаватель"})

    keyboard = create_main_keyboard(user_id)
    bot.send_message(
        user_id,
        f"✅ *{teacher_fio}*, мы вас запомнили!\n\n"
        f"Теперь вы можете:\n"
        f"• Использовать панель преподавателя\n"
        f"• Просматривать расписание групп\n"
        f"• Настроить ежедневную рассылку\n\n"
        f"Используйте кнопки ниже или команды:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def process_teacher_fio_change(message):
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

# ================== ИЗМЕНЕНИЕ ВРЕМЕНИ РАССЫЛКИ ==================

def process_change_time(message):
    user_id = int(message.from_user.id)
    text = message.text.strip()
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

# =================== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ===================

@bot.message_handler(func=lambda message: True, content_types=['text', 'document'])
def text_message_handler(message):
    user_id = int(message.from_user.id)

    # --- Загрузка файлов (DOCX/JSON) админом ---
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

        # --- JSON файл ---
        if fname.endswith('.json'):
            try:
                json.loads(file_bytes.decode('utf-8'))
                pending_uploads[user_id]['json'] = file_bytes

                # Проверяем, есть ли уже DOCX
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

            # Проверяем, есть ли JSON
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
        
        # --- Проверка: если есть оба файла, показать кнопку ---
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

    # --- Текстовые кнопки и команды ---
    text = (message.text or '').strip()
    user_role = get_user_role(user_id)

    # Админская «Пропустить»
    if text == "⏩ Пропустить" and is_admin(user_id):
        api_update_user(user_id, {"group_name": "Админ"})
        keyboard = create_main_keyboard(user_id)
        bot.send_message(
            user_id,
            "✅ Регистрация завершена!\n"
            "👑 Вы зарегистрированы как администратор\n\n"
            "Теперь вы можете использовать все функции бота:",
            reply_markup=keyboard
        )
        return

    # Выбор группы
    if text in set(api_get_all_groups()):
        if is_teacher(user_id):
            group_name = text
            sch = api_get_schedule(group_name)
            schedule_text = format_schedule_for_day(group_name, sch or {}, get_current_day() or "Понедельник")
            bot.send_message(user_id, schedule_text)
            return
        # Студентам — назначить группу
        api_update_user(user_id, {'role': 'student', 'group_name': text})
        keyboard = create_main_keyboard(user_id)
        role_text = "👨‍🎓 Студент"
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

    # Спец-кнопки
    if text == "👑 Админ панель" and is_admin(user_id):
        admin_command(message)
        return
    if text == "👨‍🏫 Панель преподавателя" and is_teacher(user_id):
        teacher_command(message)
        return

    # Основные кнопки
    if text == "📅 Сегодня":
        if is_teacher(user_id):
            teacher_fio = (api_get_user(user_id) or {}).get('teacher_fio')
            today = get_current_day()
            fio_key = fio_full_to_initials(teacher_fio or '')
            if not today:
                tomorrow = get_tomorrow_day()
                if tomorrow:
                    sch = api_get_teacher_schedule(fio_key)
                    t = format_teacher_schedule_for_day(teacher_fio or '', sch or {}, tomorrow)
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
            bot.send_message(user_id, schedule_text)
        return

    if text == "⚙️ Настройки":
        settings_command(message)
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
        bot.send_message(user_id, schedule_text)
        return

    if text == "❌ Отмена":
        pending_uploads.pop(user_id, None)
        group_name = (api_get_user(user_id) or {}).get('group_name')
        if group_name:
            keyboard = create_main_keyboard(user_id)
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

        resp = api_upload_schedule(data['docx'], None)  # JSON не передаём
        pending_uploads.pop(user_id, None)

        keyboard = create_main_keyboard(user_id)  # ← возвращаем основную клавиатуру

        if resp is not None:
            bot.send_message(user_id, "✅ Расписание успешно обновлено!", reply_markup=keyboard)
            users = api_get_users()
            for u in users:
                try:
                    bot.send_message(u["user_id"], "📢 Расписание обновлено! Проверьте своё расписание в боте.")
                except Exception:
                    pass
        else:
            bot.send_message(user_id, "❌ Ошибка при загрузке расписания.", reply_markup=keyboard),
        return
    
    if text == "📤 Загрузить оба файла":
        data = pending_uploads.get(user_id)
        if not data or 'docx' not in data:
            bot.send_message(user_id, "❌ Сначала отправьте DOCX и JSON файлы.")
            return

        bot.send_message(user_id, "⏳ Отправка файлов на сервер...")

        resp = api_upload_schedule(data['docx'], data.get('json'))
        pending_uploads.pop(user_id, None)

        keyboard = create_main_keyboard(user_id)  # ← возвращаем основную клавиатуру

        if resp is not None:
            bot.send_message(user_id, "✅ Расписание успешно обновлено!", reply_markup=keyboard)

            # Рассылка пользователям
            users = api_get_users()
            for u in users:
                uid = u.get("user_id")
                try:
                    bot.send_message(uid, "📢 Расписание обновлено! Проверьте своё расписание.")
                except Exception:
                    pass
        else:
            bot.send_message(user_id, "❌ Ошибка при загрузке расписания.", reply_markup=keyboard),
        return

    # Если ни одна команда не подошла
    bot.send_message(
        user_id,
        "❌ Неизвестная команда. Используйте кнопки или команды:\n"
        "/start - начать работу\n"
        "/schedule - расписание на сегодня\n"
        "/tomorrow - расписание на завтра\n"
        "/settings - настройки"
    )

def send_daily_schedule():
    now = datetime.now().strftime("%H:%M")
    users = api_get_users()
    for u in users:
        if not u.get("schedule_enabled"):
            continue
        if u.get("schedule_time") != now:
            continue

        uid = u.get("user_id")
        role = u.get("role")
        try:
            if role in ("teacher", "admin"):
                teacher_fio = u.get("teacher_fio")
                fio_key = fio_full_to_initials(teacher_fio or "")
                today = get_current_day()
                if not today:
                    continue
                sch = api_get_teacher_schedule(fio_key)
                text = format_teacher_schedule_for_day(teacher_fio or "", sch or {}, today)
                bot.send_message(uid, f"📅 Ваше расписание на сегодня:\n\n{text}")
            else:
                group = u.get("group_name")
                if not group:
                    continue
                today = get_current_day()
                if not today:
                    continue
                sch = api_get_schedule(group)
                text = format_schedule_for_day(group, sch or {}, today)
                bot.send_message(uid, f"📅 Ваше расписание на сегодня:\n\n{text}")
        except Exception as e:
            print(f"Ошибка отправки расписания пользователю {uid}: {e}")

# ------------------------------- РАССЫЛКА ЗАДАНИЯ ОТ ПРЕПОДАВАТЕЛЯ ------------------------------ #

@bot.callback_query_handler(func=lambda call: call.data == "teacher_lessons")
def teacher_lessons_handler(call):
    user_id = call.from_user.id
    user = api_get_user(user_id) or {}
    teacher_fio = user.get("teacher_fio")
    fio_key = fio_full_to_initials(teacher_fio or "")
    today = get_current_day()
    sch = api_get_teacher_schedule(fio_key) or {}
    schedule = sch.get("schedule", {})

    # Собираем группы из обеих смен
    groups = set()
    for shift_name, shift_data in schedule.items():
        day_lessons = shift_data.get(today, {})
        for num, info in day_lessons.items():
            group = info.get("group")
            if group:
                groups.add(group)

    kb = types.InlineKeyboardMarkup(row_width=2)
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
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("teacher_sendtask_"))
def teacher_send_task_start(call):
    user_id = call.from_user.id
    group = call.data.replace("teacher_sendtask_", "")
    msg = bot.send_message(
        user_id,
        f"📎 Прикрепите файл с заданием для группы *{group}* (документ, фото, архив и т.п.):",
        parse_mode="Markdown"
    )
    # сохраняем группу в контекст
    bot.register_next_step_handler(msg, lambda m: process_teacher_task_file(m, group))

def process_teacher_task_file(message, group_name):
    user_id = message.from_user.id
    user = api_get_user(user_id) or {}
    teacher_fio = user.get("teacher_fio", "Неизвестно")

    if message.content_type not in ["document", "photo"]:
        msg = bot.send_message(user_id, "❌ Отправьте, пожалуйста, файл или фото.")
        bot.register_next_step_handler(msg, lambda m: process_teacher_task_file(m, group_name))
        return

    # Получаем всех пользователей этой группы
    users = [u for u in api_get_users() if u.get("group_name") == group_name]
    count_sent = 0

    if message.content_type == "document":
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
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

# =================== ЗАПУСК ===================
if __name__ == "__main__":
    print("🤖 Бот запущен! Подключен к API:", API_URL)
    print(f"👑 Администраторы: {ADMINS}")
    check_api_connection()

    # 1) Снять webhook один раз
    try:
        bot.remove_webhook()
        # Если хотите сбросить очередь старых апдейтов, раскомментируйте блок ниже:
        # import requests
        # requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
        #              params={"drop_pending_updates": "true"}, timeout=10)
        time.sleep(1)  # крошечная пауза
    except Exception as e:
        print("remove_webhook error:", e)

    # Планировщик
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_daily_schedule, "interval", minutes=1)
    scheduler.start()

    # 2) Основной цикл
    while True:
        try:
            bot.polling(
                none_stop=True,
                timeout=60,
                long_polling_timeout=60,
                allowed_updates=["message", "callback_query", "document"],
                # skip_pending=True,  # ← включите, если есть такой параметр в вашей версии
            )
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            print("🔄 Перезапуск через 10 секунд...")
            time.sleep(10)
