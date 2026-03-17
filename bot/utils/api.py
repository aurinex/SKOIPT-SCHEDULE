from typing import Any, Dict, List, Optional, Tuple
from requests.adapters import HTTPAdapter, Retry
import requests
from config import API_URL, PLATFORM
from .logger import log_error

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

def api_get_user(user_id: int, platform: str = PLATFORM) -> Optional[Dict[str, Any]]:
    try:
        # Эндпоинт включает динамическую платформу[cite: 9]
        r = _get(f"{API_URL}/users/{platform}/{user_id}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users/{platform}/{user_id} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_get_user({user_id}, {platform})", e)
    return None

def api_create_user(user_id: int, role: str = "student", username: str = "", platform: str = PLATFORM) -> Optional[Dict[str, Any]]:
    # Данные для создания пользователя с указанием платформы[cite: 9]
    payload = {"user_id": user_id, "role": role, "username": username, "platform": platform}
    try:
        r = _post(f"{API_URL}/users/", json=payload)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] POST /users/ → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_create_user({user_id}, {platform})", e)
    return None

def api_update_user(user_id: int, data: Dict[str, Any], platform: str = PLATFORM) -> Optional[Dict[str, Any]]:
    try:
        # Обновление данных пользователя через платформу[cite: 9]
        r = _put(f"{API_URL}/users/{platform}/{user_id}", json=data)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] PUT /users/{platform}/{user_id} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_update_user({user_id}, {platform})", e)
    return None

def api_get_users(platform: str = PLATFORM) -> List[Dict[str, Any]]:
    try:
        params = {"skip": 0, "limit": 1000}
        # Получение списка пользователей по платформе[cite: 9]
        r = _get(f"{API_URL}/users/platform/{platform}", params=params)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users/platform/{platform} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_get_users({platform})", e)
    return []

def api_get_users_page(skip: int = 0, limit: int = 10, platform: str = PLATFORM) -> List[Dict[str, Any]]:
    try:
        # Пагинация пользователей для конкретной платформы[cite: 9]
        r = _get(f"{API_URL}/users/platform/{platform}", params={"skip": skip, "limit": limit})
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users/platform/{platform}?skip={skip}&limit={limit} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_get_users_page(skip={skip}, limit={limit}, platform={platform})", e)
    return []

def api_get_users_page_peek(skip: int = 0, limit: int = 10, platform: str = PLATFORM) -> Tuple[List[Dict[str, Any]], bool]:
    rows = api_get_users_page(skip=skip, limit=limit + 1, platform=platform)
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

        import re
        def key_fn(g: str):
            m = re.match(r"(\d+)", g)
            course = int(m.group(1)) if m else 0
            m2 = re.match(r"\d+\s*([А-Яа-яA-Za-z]*)", g)
            suf = m2.group(1) if m2 else g
            return (course, suf)
        return sorted(list(dict.fromkeys(groups)), key=key_fn)
    except Exception as e:
        log_error("api_get_all_groups()", e)
        return []

def api_get_schedule(group_name: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/schedule/{group_name}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /schedule/{group_name} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_get_schedule({group_name})", e)
    return None

def api_get_teacher_schedule(fio_key: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get(f"{API_URL}/schedule/teacher/{fio_key}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /schedule/teacher/{fio_key} → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log_error(f"api_get_teacher_schedule({fio_key})", e)
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
        print("Ошибка:", resp.text)
    except Exception as e:
        log_error("api_upload_schedule()", e)
    return None

def check_api_connection(platform: str = PLATFORM):
    try:
        print(f"🔍 Проверка API-доступности: {API_URL}")
        # Проверка соединения по платформе из конфига[cite: 9, 11]
        r = _get(f"{API_URL}/users/platform/{platform}")
        if r.status_code == 200:
            print(f"✅ API доступно для платформы {platform}!")
        else:
            print(f"⚠️ API ответило с кодом {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log_error("check_api_connection()", e)
        print("❌ Не удалось подключиться к API.")

def api_upload_bell_schedule(json_bytes: bytes):
    files = {
        "file": ("bell_schedule.json", json_bytes, "application/json"),
    }
    try:
        resp = _post(f"{API_URL}/bell_schedule/upload", files=files)
        if resp.status_code == 200:
            return resp.json()
        print("Ошибка при загрузке звонков:", resp.text)
    except Exception as e:
        log_error("api_upload_bell_schedule()", e)
    return None

def api_get_users_to_notify(time_str: str, platform: str = PLATFORM) -> List[Dict[str, Any]]:
    """Получает список пользователей, которым нужно отправить расписание в указанное время."""
    try:
        # Эндпоинт согласно схеме: /users/schedule/send/{platform}/{time}
        r = _get(f"{API_URL}/users/schedule/send/{platform}/{time_str}")
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] GET /users/notify/{platform}/{time_str} → {r.status_code}")
    except Exception as e:
        log_error(f"api_get_users_to_notify({time_str}, {platform})", e)
    return []