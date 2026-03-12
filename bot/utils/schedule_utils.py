from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import DAYS_RU, TZ

DAY_PREP_CASE = {
    "Понедельник": "в понедельник",
    "Вторник":     "во вторник",
    "Среда":       "в среду",
    "Четверг":     "в четверг",
    "Пятница":     "в пятницу",
    "Суббота":     "в субботу",
    "Воскресенье": "в воскресенье",
}

def lesson_sort_key(num: str):
    return [int(x) for x in num.split(".")]

def in_day_ru(day: str) -> str:
    """Возвращает 'в понедельник/во вторник/в среду/...' (с маленькой буквы)."""
    return DAY_PREP_CASE.get(day, f"в {day.lower()}")

def format_lesson_number(num: str):
    parts = num.split(".")
    base = parts[0]
    half = None
    subgroup = None

    if len(parts) >= 2:
        half = parts[1]
    if len(parts) == 3:
        subgroup = parts[2]
    return base, half, subgroup

def get_current_day() -> Optional[str]:
    today = datetime.now(ZoneInfo(TZ)).weekday()
    if today == 6:
        return None
    return DAYS_RU[today]

def get_tomorrow_day() -> Optional[str]:
    tomorrow_date = datetime.now(ZoneInfo(TZ)) + timedelta(days=1)
    wd = tomorrow_date.weekday()
    if wd == 6:
        return None
    return DAYS_RU[wd]

def format_schedule_for_day(group_name: str, schedule_doc: Dict[str, Any], day: str) -> str:
    if not schedule_doc:
        return "❌ Расписание для вашей группы не найдено"
    schedule = schedule_doc.get('schedule', {})
    zero_lesson = (schedule.get('zero_lesson') or {}).get(day, {})
    day_lessons = (schedule.get('days') or {}).get(day, {})
    if not zero_lesson and not day_lessons:
        return f"📅 {in_day_ru(day).capitalize()} пар нет"
    result = f"📚 Расписание на {day} ({group_name}):\n\n"
    lessons_today: List[str] = []
    # Нулевая пара
    if zero_lesson:
        subject = zero_lesson.get('subject', '')
        classroom = zero_lesson.get('classroom', '')
        teacher = zero_lesson.get('teacher', '')
        time_str = zero_lesson.get('time')
        if subject:
            lesson_text = f"0. {subject}"
            if classroom:
                lesson_text += f" {classroom} каб."
            if teacher:
                lesson_text += f" ({teacher})"
            if time_str:
                lesson_text += f"\n 🕒 {time_str}"
            lessons_today.append(lesson_text)
            
    # Основные пары
    for lesson_num, lesson_info in sorted((day_lessons or {}).items(), key=lambda x: lesson_sort_key(x[0])):
        subject = lesson_info.get('subject', '')
        classroom = lesson_info.get('classroom', '')
        teacher = lesson_info.get('teacher', '')
        time_str = lesson_info.get('time')

        if not subject:
            continue

        base, half, subgroup = format_lesson_number(lesson_num)

        if half == "2":
            if subgroup:
                lesson_text = f"   [2/2] ({subgroup} гр) "
            else:
                lesson_text = "   [2/2] "
        else:
            lesson_text = f"{base}. "
            if half == "1":
                lesson_text += "[1/2] "

        lesson_text += subject

        if classroom:
            lesson_text += f" {classroom} каб"

        if teacher:
            lesson_text += f" ({teacher})"

        if time_str:
            lesson_text += f"\n 🕒 {time_str}"

        lessons_today.append(lesson_text)
            
    if not lessons_today:
        return f"📅 {in_day_ru(day).capitalize()} пар нет"
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

        for num, info in sorted(day_dict.items(), key=lambda x: lesson_sort_key(x[0])):
            subject = info.get('subject', '')
            group = info.get('group', '')
            room = info.get('classroom', '')
            time_str = info.get('time')

            base, half, subgroup = format_lesson_number(num)

            if half == "2":
                if subgroup:
                    line = f"   [2/2] ({subgroup} гр) {subject}"
                else:
                    line = f"   [2/2] {subject}"
            else:
                line = f"{base}. "
                if half == "1":
                    line += "[1/2] "
                line += subject

            if group:
                line += f" — {group}"

            if room:
                line += f" ({room} каб.)"

            if time_str:
                line += f"\n 🕒 {time_str}"

            if shift_name == 'first_shift':
                first_shift.append(line)
            else:
                second_shift.append(line)

    if not first_shift and not second_shift:
        return f"📅 {in_day_ru(day).capitalize()} пар нет"

    result = f"👨‍🏫 Расписание преподавателя\n{teacher_full_fio}\n\n📅 {day}\n\n"

    # если есть только первая смена
    if first_shift and not second_shift:
        result += "\n".join(first_shift)
        return result

    # если есть обе смены
    if first_shift:
        result += "1️⃣ Первая смена:\n" + "\n".join(first_shift)

    if second_shift:
        result += "\n\n2️⃣ Вторая смена:\n" + "\n".join(second_shift)

    return result