import os
from dotenv import load_dotenv

load_dotenv()

# Base config
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
API_URL: str = os.getenv("API_URL", "http://172.17.0.1:3020")
TZ: str = os.getenv("TZ", "Asia/Yekaterinburg")

# Roles
ROLES = {
    'student': '👨‍🎓 Студент',
    'teacher': '👨‍🏫 Преподаватель',
    'admin':   '👑 Администратор'
}

# Admin user ids
ADMINS = [1044229010, 965614231, 816355942]

# Weekdays (Russian)
DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]