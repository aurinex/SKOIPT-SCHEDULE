from config import ROLES

def welcome_text(is_admin: bool, is_teacher: bool) -> str:
    txt = "👋 Добро пожаловать в бот расписания Салаватского колледжа\n\n"
    if is_admin:
        txt += "Вы можете выбрать группу или нажать 'Пропустить'\n\n"
    elif is_teacher:
        txt += "Выберите группу для просмотра расписания:\n\n"
    else:
        txt += "📚 Выберите вашу группу из списка ниже:"
    return txt

def settings_text(user_role: str, current_group: str, schedule_enabled: bool, sched_time: str, teacher_fio: str | None) -> str:
    schedule_status = "включена" if schedule_enabled else "отключена"
    teacher_info = f"👨‍🏫 ФИО: {teacher_fio}\n" if teacher_fio else ""
    return (
        f"⚙️ Настройки | {ROLES.get(user_role, user_role)}\n\n"
        f"{teacher_info}"
        f"📚 Текущая группа: {current_group}\n"
        f"🔔 Ежедневная рассылка: {schedule_status}\n"
        f"⏰ Время отправки: {sched_time}"
    )