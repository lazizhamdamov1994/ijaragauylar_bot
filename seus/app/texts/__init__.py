"""Bot matnlari. Hozir faqat o'zbekcha; rus tili uchun ru.py qo'shiladi va LANGS'ga yoziladi."""
from app.texts import uz

LANGS: dict[str, dict[str, str]] = {"uz": uz.TEXTS}
DEFAULT_LANG = "uz"


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    texts = LANGS.get(lang) or LANGS[DEFAULT_LANG]
    template = texts.get(key) or LANGS[DEFAULT_LANG][key]
    return template.format(**kwargs) if kwargs else template


def all_langs(key: str) -> set[str]:
    """Tugma matni qaysi tilda bo'lsa ham tanib olish uchun."""
    return {texts[key] for texts in LANGS.values() if key in texts}
