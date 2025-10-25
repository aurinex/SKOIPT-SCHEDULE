from datetime import datetime
from zoneinfo import ZoneInfo
import traceback

def log_error(context: str, e: Exception, tz: str = "Asia/Yekaterinburg"):
    print(f"\n[❌ {datetime.now(ZoneInfo(tz)).strftime('%Y-%m-%d %H:%M:%S')}] Ошибка в {context}:")
    print(f"Тип: {type(e).__name__}")
    print(f"Описание: {e}")
    tb = traceback.format_exc(limit=2)
    print(f"Трассировка: {tb}\n")