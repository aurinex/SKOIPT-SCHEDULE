import re

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