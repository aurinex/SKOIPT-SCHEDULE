from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from zoneinfo import ZoneInfo
from bot.core import bot
from bot.utils.api import api_get_users, api_get_schedule, api_get_teacher_schedule
from bot.utils.schedule_utils import get_current_day, format_schedule_for_day, format_teacher_schedule_for_day
from bot.utils.fio_utils import fio_full_to_initials
from config import TZ

def send_daily_schedule():
    now = datetime.now(ZoneInfo(TZ)).strftime("%H:%M")
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
                bot.send_message(uid, f"📅 Ваше расписание на сегодня:\n\n{text}", protect_content=True)
        except Exception as e:
            print(f"Ошибка отправки расписания пользователю {uid}: {e}")

def attach_and_start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_daily_schedule, "interval", minutes=1)
    scheduler.start()
    return scheduler