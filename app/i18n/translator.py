from app.i18n.locales.uk import STRINGS as UK
from app.i18n.locales.ru import STRINGS as RU


LANG_MAP = {
    "uk": UK,
    "ru": RU,
}


def t(key: str, locale: str) -> str:
    lang = LANG_MAP.get(locale, UK)
    return lang.get(key, key)


def label(locale: str) -> str:
    if locale == "ru":
        return "Русский"
    return "Українська"
