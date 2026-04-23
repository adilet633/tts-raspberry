import re
from enum import Enum
from typing import Dict, Tuple, Any, List, Optional
from difflib import SequenceMatcher
import math


class Intent(str, Enum):
    HELP = "help"
    TIME = "time"
    DATE = "date"
    REMINDER = "reminder"
    READ_CLIPBOARD = "read_clipboard"
    NOTE = "note"
    SOS = "sos"
    SWITCH_LANG = "switch_lang"
    EXIT = "exit"
    CHAT = "chat"
    UNKNOWN = "unknown"
    MEMORY_READ = "memory_read"
    CONTACT_RELATIVE = "contact_relative"


def _clean(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _best_match(text: str, phrases: List[str]) -> float:
    t = _clean(text)
    best = 0.0
    for p in phrases:
        p2 = _clean(p)
        if not p2:
            continue
        if p2 in t:
            best = max(best, 1.0)
            continue
        best = max(best, _sim(t, p2))
    return best


def _strip_punct(s: str) -> str:
    return (s or "").strip(" \t\n\r,.;:!?-–—()[]{}\"'")


def _minutes_from_amount_unit(amount: float, unit: str) -> int:
    unit = _clean(unit)
    minutes = None

    # RU/EN
    if unit in ("сек", "с", "секунд", "секунда", "секунды", "sec", "secs", "second", "seconds"):
        minutes = amount / 60.0
    elif unit in ("мин", "м", "минут", "минута", "минуты", "minute", "minutes", "min", "mins"):
        minutes = amount
    elif unit in ("час", "часа", "часов", "hour", "hours", "hr", "hrs"):
        minutes = amount * 60.0
    elif unit in ("день", "дня", "дней", "day", "days"):
        minutes = amount * 1440.0

    # KZ
    elif unit in ("сағат", "сағ", "сағаттар"):
        minutes = amount * 60.0
    elif unit in ("күн", "күндер"):
        minutes = amount * 1440.0

    if minutes is None:
        return 1
    return max(1, int(math.ceil(minutes)))


# -------------------------
# Number words (RU) -> int
# -------------------------
_RU_ONES = {
    "ноль": 0,
    "один": 1, "одна": 1, "одно": 1,
    "два": 2, "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,

    "девять": 9,
}
_RU_TEENS = {
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
}
_RU_TENS = {
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
}
_RU_HUNDREDS = {
    "сто": 100,
    "двести": 200,
    "триста": 300,
    "четыреста": 400,
    "пятьсот": 500,
    "шестьсот": 600,
    "семьсот": 700,
    "восемьсот": 800,
    "девятьсот": 900,
}


def _parse_ru_number_words(tokens: List[str]) -> Optional[int]:
    """
    Parses a small Russian number phrase from tokens.
    Supports:
      - пять
      - двадцать пять
      - сто двадцать три
    Returns int or None.
    """
    if not tokens:
        return None

    total = 0
    i = 0

    # hundreds
    if i < len(tokens) and tokens[i] in _RU_HUNDREDS:
        total += _RU_HUNDREDS[tokens[i]]
        i += 1

    # teens
    if i < len(tokens) and tokens[i] in _RU_TEENS:
        total += _RU_TEENS[tokens[i]]
        i += 1
        return total if total > 0 else None

    # tens
    if i < len(tokens) and tokens[i] in _RU_TENS:
        total += _RU_TENS[tokens[i]]
        i += 1
        # optional ones
        if i < len(tokens) and tokens[i] in _RU_ONES:
            total += _RU_ONES[tokens[i]]
            i += 1
        return total if total > 0 else None

    # ones
    if i < len(tokens) and tokens[i] in _RU_ONES:
        total += _RU_ONES[tokens[i]]
        i += 1
        return total

    return None


def _find_number_ru(s: str) -> Tuple[Optional[int], str]:
    """
    Find first number either as digits or as RU words in a string.
    Returns (number, rest_after_number).
    """
    s = _clean(s)

    # digits first
    m = re.search(r"\b(\d{1,4})\b", s)
    if m:
        n = int(m.group(1))
        rest = s[m.end():].strip()
        return n, rest

    # words: scan tokens and try 1-3 token window
    toks = s.split()
    for start in range(len(toks)):
        for length in (3, 2, 1):
            chunk = toks[start:start+length]
            n = _parse_ru_number_words(chunk)
            if n is not None:
                # rebuild rest string after that chunk
                rest_toks = toks[start+length:]
                rest = " ".join(rest_toks).strip()
                return n, rest
    return None, s


# -------------------------
# Dictionaries (expanded)
# -------------------------
RU = {
    "help": ["помощь", "справка", "что ты умеешь", "команды", "помоги", "что умеешь"],
    "time": ["время", "который час", "сколько времени", "какое сейчас время", "time", "what time"],
    "date": ["дата", "какое сегодня число", "какой сегодня день", "какая сегодня дата", "date", "today date"],
    "memory_read": [
        "прочитай мои заметки",
        "прочитай заметки",
        "что я записал",
        "покажи мои заметки",
        "какие у меня заметки"
    ],
    "exit": ["выход", "выйти", "закрыть", "завершить", "стоп", "пока", "до свидания"],
    "sos": [
        "сос",
        "sos",
        "нужна помощь",
        "помоги мне",
        "мне плохо",
        "мне нужна помощь",
        "вызови помощь",
        "позови на помощь",
        "экстренная помощь",
        "тревога",
        "alarm",
        "экстренно"
    ],
    "read_clipboard": ["прочитай буфер", "буфер обмена", "прочитай текст", "clipboard"],
    "contact_relative": [
        "свяжись с родственником",
        "свяжись с близкими",
        "позови родственника",
        "позови близких",
        "отправь сообщение родственнику",
        "отправь сообщение семье",
        "сообщи родственникам",
        "сообщи семье",
        "свяжись с семьей",
        "позвони родственнику"
    ],
    "note": [
        "заметка",
        "запиши",
        "запиши заметку",
        "добавь заметку",
        "сделай заметку",
        "запомни",
        "запомни что",
        "сохрани",
        "сохрани заметку",
        "запиши что",
        "note"
    ],
    "switch_kz": ["переключи на казахский", "на казахский", "казахский язык", "қазақша", "kz", "kazakh"],
    "switch_ru": ["переключи на русский", "на русский", "русский язык", "орысша", "ru", "russian"],
}

KZ = {
    "help": ["анықтама", "не істей аласың", "командалар"],
    "time": ["сағат", "сағат қанша", "уақыт", "time"],
    "memory_read": [
        "жазбаларымды оқы",
        "жазбаларды оқы",
        "не жазып қойдым",
        "менің жазбаларымды айт",
        "қандай жазбаларым бар"
    ],
    "date": ["күн", "бүгін қай күн", "дата", "date"],
    "contact_relative": [
        "туысқаныма хабарлас",
        "жақындарыма хабарлас",
        "отбасыма хабар бер",
        "туыстарыма хабар бер",
        "отбасыма хабарла",
        "жақындарыма хабарла",
        "туысқаныма хабар жібер"
    ],
    "exit": ["шығу", "тоқта", "жабу", "аяқта", "сөндір", "өшір"],
    "sos": [
        "сос",
        "sos",
        "көмек керек",
        "маған көмек керек",
        "маған жаман болып тұр",
        "жедел көмек шақыр",
        "көмек шақыр",
        "дабыл",
        "жедел көмек"
    ],
    "read_clipboard": ["буферді оқы", "алмасу буфері", "мәтінді оқы", "clipboard"],
    "note": [
        "жазып қой",
        "жазба",
        "ескертпе",
        "жазып ал",
        "есте сақта",
        "сақтап қой",
        "жазып қойшы",
        "мынаны жазып қой",
        "note"
    ],
    "switch_kz": ["қазақшаға ауыс", "қазақ тіліне ауыс", "қазақша", "kz"],
    "switch_ru": ["орысшаға ауыс", "орыс тіліне ауыс", "орысша", "ru", "русский"],
}

_RU_REMIND_VERB = r"(?:напомн\w*|постав\w*\s+напоминан\w*|установ\w*\s+напоминан\w*|созда\w*\s+напоминан\w*|сдела\w*\s+напоминан\w*|таймер|постав\w*\s+таймер)"
_RU_AFTER_WORD = r"(?:через|спустя|после|по\s+истечени[юя])"


def _extract_reminder_text(raw_tail: str) -> str:
    s = _clean(raw_tail)
    s = _strip_punct(s)
    s = re.sub(r"^(?:что\s+|чтобы\s+|мне\s+|пожалуйста\s+|пж\s+)", "", s).strip()
    return s or ""

def _remove_reminder_words(s: str) -> str:
    s = _clean(s)
    s = re.sub(rf"\b{_RU_REMIND_VERB}\b", "", s)
    return _strip_punct(s).strip()

def _normalize_unit_ru(u: str) -> str:
    u = _clean(u)
    if u == "с":
        return "сек"
    if u in ("мин", "м"):
        return "мин"
    return u


def _parse_reminder_ru(t: str) -> Tuple[bool, Dict[str, Any]]:
    s = _clean(t)

    # "напомни принять лекарство через минуту"
    m = re.search(rf"(?P<prefix>.*?)\b{_RU_AFTER_WORD}\s+минут\w*\b(?P<suffix>.*)$", s)
    if m:
        prefix = _remove_reminder_words(m.group("prefix"))
        suffix = _extract_reminder_text(m.group("suffix"))
        tail = (prefix + " " + suffix).strip()
        return True, {"minutes": 1, "text": tail or "напоминание"}

    # "напомни попить воду через полчаса"
    m = re.search(rf"(?P<prefix>.*?)\b{_RU_AFTER_WORD}\s+полчаса\b(?P<suffix>.*)$", s)
    if m:
        prefix = _remove_reminder_words(m.group("prefix"))
        suffix = _extract_reminder_text(m.group("suffix"))
        tail = (prefix + " " + suffix).strip()
        return True, {"minutes": 30, "text": tail or "напоминание"}

    # "напомни лечь спать через час"
    m = re.search(rf"(?P<prefix>.*?)\b{_RU_AFTER_WORD}\s+час\b(?P<suffix>.*)$", s)
    if m:
        prefix = _remove_reminder_words(m.group("prefix"))
        suffix = _extract_reminder_text(m.group("suffix"))
        tail = (prefix + " " + suffix).strip()
        return True, {"minutes": 60, "text": tail or "напоминание"}

    # Общий случай:
    # "напомни принять лекарство через 5 минут"
    # "напомни попить воду через 20 минут"
    # "напомни поесть через 2 часа"
    m = re.search(rf"(?P<prefix>.*?)\b{_RU_AFTER_WORD}\b\s+(?P<rest>.+)$", s)
    if m:
        prefix = _remove_reminder_words(m.group("prefix"))
        rest = m.group("rest")

        num, after_num_rest = _find_number_ru(rest)
        if num is None:
            return False, {}

        unit_m = re.search(
            r"\b(секунд\w*|сек\w*|с\b|минут\w*|мин\b|м\b|час\w*|дн\w*|день|дня|дней)\b",
            after_num_rest
        )
        if not unit_m:
            return False, {}

        unit = _normalize_unit_ru(unit_m.group(1))
        suffix = after_num_rest[unit_m.end():]
        suffix = _extract_reminder_text(suffix)

        tail = (prefix + " " + suffix).strip()
        minutes = _minutes_from_amount_unit(float(num), unit)

        return True, {"minutes": minutes, "text": tail or "напоминание"}

    return False, {}

def _parse_reminder_kz(t: str) -> Tuple[bool, Dict[str, Any]]:
    s = _clean(t)
    m = re.search(r"(?P<num>\d{1,4})\s*(?P<unit>минут\w*|секунд\w*|сағат\w*|күн\w*)\s*тан?\s*(кейін|соң)\s*(?P<tail>.*)$", s)
    if m:
        num = float(m.group("num"))
        unit = m.group("unit")
        minutes = _minutes_from_amount_unit(num, unit)
        tail = _extract_reminder_text(m.group("tail") or "")
        return True, {"minutes": minutes, "text": tail or "еске салу"}
    return False, {}


def parse_intent(text: str, lang: str = "ru") -> Tuple[Intent, Dict[str, Any]]:
    t = _clean(text)
    if not t:
        return Intent.UNKNOWN, {}

    D = RU if lang == "ru" else KZ

    short = len(t) <= 6
    TH = 0.78 if short else 0.65

    # 1) reminder FIRST
    ok, payload = _parse_reminder_ru(t) if lang == "ru" else _parse_reminder_kz(t)
    if ok:
        return Intent.REMINDER, payload

    # 2) exit
    if _best_match(t, D["exit"]) >= TH:
        return Intent.EXIT, {}

    # 3) switch
    if _best_match(t, D["switch_kz"]) >= TH:
        return Intent.SWITCH_LANG, {"lang": "kz"}
    if _best_match(t, D["switch_ru"]) >= TH:
        return Intent.SWITCH_LANG, {"lang": "ru"}

    # 4) help/time/date
    if _best_match(t, D["help"]) >= TH:
        return Intent.HELP, {}
    if _best_match(t, D["time"]) >= TH:
        return Intent.TIME, {}
    if _best_match(t, D["date"]) >= TH:
        return Intent.DATE, {}

    # 5) sos/clipboard/note
    if _best_match(t, D["sos"]) >= TH:
        return Intent.SOS, {}
    if _best_match(t, D["read_clipboard"]) >= TH:
        return Intent.READ_CLIPBOARD, {}
    if _best_match(t, D["note"]) >= TH:
        for trig in D["note"]:
            trig2 = _clean(trig)
            if trig2 and trig2 in t:
                note_text = _strip_punct(t.split(trig2, 1)[-1])
                return Intent.NOTE, {"text": note_text}
        return Intent.NOTE, {"text": ""}
    if _best_match(t, D["memory_read"]) >= TH:
        return Intent.MEMORY_READ, {}
    if _best_match(t, D["contact_relative"]) >= TH:
        return Intent.CONTACT_RELATIVE, {}
    return Intent.UNKNOWN, {}

