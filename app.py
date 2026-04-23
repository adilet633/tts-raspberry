import re
import sys

from core.config_loader import load_config
from core.stt_vosk import VoskSTT
from core.reminders import ReminderManager
from core.intents import parse_intent, Intent
from core.skills import Skills

from core.tts_macos_say import MacOSSayTTS
from core.tts_espeak import EspeakTTS
from core.tts_pyttsx3 import Pyttsx3TTS

from core.tts_silero import SileroRuTTS, SileroKzTTS
from core.tts_piper import PiperTTS

from core.llm_router_ollama import OllamaRouter


def get_prompt(cfg: dict, lang: str, key: str, default_ru: str, default_kz: str) -> str:
    prompts = cfg.get("prompts", {}) or {}
    v = (prompts.get(lang, {}) or {}).get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return default_kz if lang == "kz" else default_ru


def build_tts(cfg: dict, lang: str):
    """
    Works on macOS and Raspberry Pi.
    Priority: Silero (RU + KZ), then system fallbacks.
    """
    engine = (cfg.get("tts_engine") or "auto").lower()
    rate = int(cfg.get("tts_rate", 170))

    voice_ru = (cfg.get("tts_voice_ru") or "").strip()
    voice_kz = (cfg.get("tts_voice_kz") or "").strip()

    if engine == "auto":
        engine_ru = (cfg.get("tts_engine_ru") or "silero").lower()
        engine_kz = (cfg.get("tts_engine_kz") or "silero").lower()
        engine = engine_kz if lang == "kz" else engine_ru

    if engine == "piper":
        piper_cfg = cfg.get("tts_piper", {}) or {}

        if lang == "kz":
            model_path = piper_cfg.get("kz_model", "models/piper/ru_RU-ruslan-medium.onnx")
        else:
            model_path = piper_cfg.get("ru_model", "models/piper/ru_RU-ruslan-medium.onnx")

        return PiperTTS(model_path=model_path)

    if engine == "silero":
        sil = cfg.get("tts_silero", {}) or {}
        device = sil.get("device", "cpu")
        sr = int(sil.get("sample_rate", 24000))
        cache_dir = sil.get("cache_dir")

        if lang == "kz":
            voice = voice_kz or None
            return SileroKzTTS(speaker=voice, sample_rate=sr, device=device, cache_dir=cache_dir)

        voice = voice_ru or None
        return SileroRuTTS(speaker=voice, sample_rate=sr, device=device, cache_dir=cache_dir)


    if engine == "espeak":
        voice = "ru" if lang == "ru" else "kk"
        return EspeakTTS(voice=voice, rate=rate)

    if engine in ("say", "macos"):
        mac_voice = voice_kz if lang == "kz" else voice_ru
        return MacOSSayTTS(rate=rate, voice=mac_voice)

    if engine == "pyttsx3":
        return Pyttsx3TTS(rate=rate)

    # Fallback
    if sys.platform == "darwin":
        mac_voice = voice_kz if lang == "kz" else voice_ru
        return MacOSSayTTS(rate=rate, voice=mac_voice)

    # Linux/RPi fallback
    try:
        sil = cfg.get("tts_silero", {}) or {}
        device = sil.get("device", "cpu")
        sr = int(sil.get("sample_rate", 24000))
        cache_dir = sil.get("cache_dir")
        if lang == "kz":
            return SileroKzTTS(speaker=(voice_kz or None), sample_rate=sr, device=device, cache_dir=cache_dir)
        return SileroRuTTS(speaker=(voice_ru or None), sample_rate=sr, device=device, cache_dir=cache_dir)
    except Exception:
        return Pyttsx3TTS(rate=rate)


def normalize_lang_value(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ["kz", "kk", "kaz", "kazakh", "kazak", "kazah"]:
        return "kz"
    if "қаз" in v or "каз" in v or "kaz" in v:
        return "kz"
    if v in ["ru", "rus", "russian"]:
        return "ru"
    if "рус" in v or "орыс" in v:
        return "ru"
    return ""


def should_exit(text: str, lang: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    ru_exit = ["выход", "выйти", "выйди", "закрыть", "завершить", "стоп", "остановись"]
    kz_exit = ["шығу", "тоқта", "тоқтату", "жабу", "аяқта", "аяқтау"]
    keys = kz_exit if lang == "kz" else ru_exit
    return any(k in t for k in keys)


def looks_like_garbage(text: str) -> bool:
    """
    STT garbage filter:
    - too short fragments
    - particles like 'иә/мм/бе'
    """
    t = (text or "").strip().lower()
    if not t:
        return True
    if len(t) <= 2:
        return True
    bad = {"иә", "иа", "ә", "а", "ме", "бе", "па", "ма", "мм", "эм"}
    if t in bad:
        return True
    return False


# -------------------------
# EXTRA: robust keyword checks
# -------------------------
_TIME_KEYS = [
    # RU
    "время", "который час", "сколько времени", "какое сейчас время",
    # KZ
    "сағат", "сағат қанша", "уақыт", "қазір сағат қанша",
    # EN
    "time", "what time", "tell me the time", "current time"
]

_DATE_KEYS = [
    # RU
    "дата", "какое сегодня число", "какой сегодня день", "какая сегодня дата", "сегодня число",
    # KZ
    "күн", "бүгін қай күн", "бүгінгі күн", "дата",
    # EN
    "date", "today date", "what is the date", "what's the date", "today's date"
]


def _clean_text(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def is_time_request(text: str) -> bool:
    t = _clean_text(text)
    return any(k in t for k in _TIME_KEYS)


def is_date_request(text: str) -> bool:
    t = _clean_text(text)
    return any(k in t for k in _DATE_KEYS)


# -------------------------
# EXTRA: rule-based capitals (anti-hallucination)
# -------------------------
_CAPITALS = {
    # english key -> (ru, kz, en)
    "germany": ("Берлин", "Берлин", "Berlin"),
    "austria": ("Вена", "Вена", "Vienna"),
    "france": ("Париж", "Париж", "Paris"),
    "italy": ("Рим", "Рим", "Rome"),
    "spain": ("Мадрид", "Мадрид", "Madrid"),
    "portugal": ("Лиссабон", "Лиссабон", "Lisbon"),
    "united kingdom": ("Лондон", "Лондон", "London"),
    "uk": ("Лондон", "Лондон", "London"),
    "great britain": ("Лондон", "Лондон", "London"),
    "russia": ("Москва", "Мәскеу", "Moscow"),
    "kazakhstan": ("Астана", "Астана", "Astana"),
    "china": ("Пекин", "Бейжің", "Beijing"),
    "japan": ("Токио", "Токио", "Tokyo"),
    "south korea": ("Сеул", "Сеул", "Seoul"),
    "usa": ("Вашингтон", "Вашингтон", "Washington, D.C."),
    "united states": ("Вашингтон", "Вашингтон", "Washington, D.C."),
    "turkey": ("Анкара", "Анкара", "Ankara"),
    "uae": ("Абу-Даби", "Абу-Даби", "Abu Dhabi"),
    "united arab emirates": ("Абу-Даби", "Абу-Даби", "Abu Dhabi"),
}


def detect_capital_question(text: str) -> str:
    """
    Returns normalized country key (english) if detected, else "".
    Supports:
    - "capital of germany"
    - "what is the capital of germany"
    - "столица германии"
    - "германияның астанасы"
    """
    t = _clean_text(text)

    # English: "capital of X"
    m = re.search(r"\bcapital of\s+([a-z .'-]{2,})\b", t)
    if m:
        country = m.group(1).strip()
        country = re.sub(r"[?!.]+$", "", country).strip()
        return country

    # English: "what is the capital of X"
    m = re.search(r"\bwhat(?:'s| is)\s+the\s+capital of\s+([a-z .'-]{2,})\b", t)
    if m:
        country = m.group(1).strip()
        country = re.sub(r"[?!.]+$", "", country).strip()
        return country

    # Russian: "столица X"
    m = re.search(r"\bстолица\s+([а-яё\- ]{2,})\b", t)
    if m:
        country_ru = m.group(1).strip()
        return ru_country_to_en_key(country_ru)

    # Kazakh: "X астанасы" or "X-тің астанасы" or "Xның астанасы"
    if "астанасы" in t:
        # take part before "астанасы"
        part = t.split("астанасы", 1)[0].strip()
        part = re.sub(r"(нің|ның|дің|дың|тің|тың)$", "", part).strip()
        if part:
            return kz_country_to_en_key(part)

    return ""


def ru_country_to_en_key(country_ru: str) -> str:
    c = _clean_text(country_ru)
    # very small mapping (extend if needed)
    mapping = {
        "германии": "germany",
        "германия": "germany",
        "австрии": "austria",
        "австрия": "austria",
        "франции": "france",
        "франция": "france",
        "италии": "italy",
        "италия": "italy",
        "испания": "spain",
        "испании": "spain",
        "казахстана": "kazakhstan",
        "казахстан": "kazakhstan",
        "россии": "russia",
        "россия": "russia",
        "китая": "china",
        "китай": "china",
        "японии": "japan",
        "япония": "japan",
        "турции": "turkey",
        "турция": "turkey",
        "сша": "usa",
        "соединенных штатов": "united states",
        "великобритании": "united kingdom",
        "оаэ": "uae",
    }
    return mapping.get(c, "")


def kz_country_to_en_key(country_kz: str) -> str:
    c = _clean_text(country_kz)
    mapping = {
        "германия": "germany",
        "австрия": "austria",
        "франция": "france",
        "италия": "italy",
        "испания": "spain",
        "қазақстан": "kazakhstan",
        "ресей": "russia",
        "қытай": "china",
        "жапония": "japan",
        "түркия": "turkey",
        "аҚш": "usa",
        "ақш": "usa",
        "британия": "united kingdom",
        "біріккен корольдік": "united kingdom",
        "баә": "uae",
    }
    return mapping.get(c, "")


def answer_capital(country_key: str, lang: str) -> str:
    key = _clean_text(country_key)
    # normalize some common variants
    key = key.replace("the ", "").strip()
    key = key.replace("republic of ", "").strip()

    # exact match
    if key in _CAPITALS:
        ru, kz, en = _CAPITALS[key]
        if lang == "kz":
            return kz
        if lang == "ru":
            return ru
        return en

    # try contains match (e.g., "germany?" already cleaned)
    for k in _CAPITALS.keys():
        if key == k:
            ru, kz, en = _CAPITALS[k]
            return kz if lang == "kz" else (ru if lang == "ru" else en)

    return ""


def switch_language(new_lang: str, cfg: dict, vosk_models: dict, stt: VoskSTT,
                    reminders: ReminderManager, skills: Skills):
    if new_lang not in vosk_models:
        skills.tts.say(get_prompt(cfg, cfg.get("language", "ru"), "model_not_found",
                                  "Модель для этого языка не найдена.",
                                  "Бұл тілге модель табылмады."))
        return False

    try:
        stt.load_model(vosk_models[new_lang])
    except Exception as e:
        skills.tts.say(get_prompt(cfg, cfg.get("language", "ru"), "switch_failed",
                                  "Не удалось переключить язык. Проверьте папку модели.",
                                  "Тілді ауыстыру мүмкін болмады. Модель папкасын тексеріңіз."))
        print("ERROR switching Vosk model:", e)
        return False

    # rebuild TTS
    try:
        tts = build_tts(cfg, new_lang)
        reminders.tts = tts
        skills.tts = tts
        skills.lang = new_lang
    except Exception as e:
        print("ERROR rebuilding TTS:", e)

    cfg["language"] = new_lang
    if new_lang == "kz":
        skills.tts.say(get_prompt(cfg, "kz", "switched_ok",
                                  "Переключился на казахский.",
                                  "Қазақ тіліне ауыстым."))
    else:
        skills.tts.say(get_prompt(cfg, "ru", "switched_ok",
                                  "Переключился на русский.",
                                  "Орыс тіліне ауыстым."))
    return True


def main():
    cfg = load_config("config.json")

    vosk_models = cfg.get("vosk_models", {}) or {}
    lang = (cfg.get("language") or "ru").lower()
    if lang not in vosk_models:
        lang = "ru"

    tts = build_tts(cfg, lang)

    stt = VoskSTT(
        model_path=vosk_models[lang],
        sample_rate=int(cfg.get("sample_rate", 16000)),
    )

    reminders = ReminderManager(tts)
    reminders.start()
    skills = Skills(
        tts=tts,
        reminders=reminders,
        notes_file=cfg.get("notes_file", "notes.txt"),
        sos_cfg=cfg.get("sos", {}),
        lang=lang,
    )

    llm = OllamaRouter(cfg.get("llm", {}))

    skills.tts.say(get_prompt(cfg, lang, "boot",
                              "Голосовой помощник запущен. Нажмите Enter и говорите.",
                              "Дауыс көмекші іске қосылды. Enter басып, сөйлеңіз."))

    listen_seconds = int(cfg.get("listen_seconds", 6))

    while True:

        input("\nEnter -> говорить... ")

        skills.tts.say(get_prompt(cfg, lang, "listening", "Слушаю.", "Тыңдап тұрмын."))

        text = stt.listen_text(seconds=listen_seconds)
        print("YOU:", text)

        # hard-exit before everything
        if should_exit(text, lang=lang):
            skills.tts.say(get_prompt(cfg, lang, "bye",
                                      "Завершаю работу. До свидания.",
                                      "Жұмысты аяқтаймын. Сау болыңыз."))
            break

        # EXTRA: force time/date even if parse_intent fails (English/mixed STT)
        if is_time_request(text):
            skills.do_time()
            continue

        if is_date_request(text):
            skills.do_date()
            continue

        intent, payload = parse_intent(text, lang="ru")
        if intent == Intent.UNKNOWN:
            intent, payload = parse_intent(text, lang="kz")

        # --- rule-based commands only ---
        if intent == Intent.EXIT:
            skills.tts.say(get_prompt(cfg, lang, "bye",
                                      "Завершаю работу. До свидания.",
                                      "Жұмысты аяқтаймын. Сау болыңыз."))
            break

        if intent == Intent.HELP:
            skills.do_help()
            continue

        if intent == Intent.TIME:
            skills.do_time()
            continue

        if intent == Intent.DATE:
            skills.do_date()
            continue

        if intent == Intent.REMINDER:
            skills.do_reminder(int(payload["minutes"]), payload["text"])
            continue

        if intent == Intent.READ_CLIPBOARD:
            skills.do_read_clipboard()
            continue

        if intent == Intent.NOTE:
            skills.do_note(payload.get("text", ""))
            continue

        if intent == Intent.MEMORY_READ:
            skills.do_memory_read()
            continue

        if intent == Intent.CONTACT_RELATIVE:
            skills.do_contact_relative()
            continue

        if intent == Intent.SOS:
            skills.do_sos()
            continue

        if intent == Intent.SWITCH_LANG:
            new_lang = payload.get("lang", "ru")
            if not switch_language(new_lang, cfg, vosk_models, stt, reminders, skills):
                continue
            lang = new_lang
            continue

        # --- UNKNOWN: apply rule-based "capital of" to prevent hallucinations ---
        country_key = detect_capital_question(text)
        if country_key:
            cap = answer_capital(country_key, lang=lang)
            if cap:
                skills.tts.say(cap)
                continue
            # If country not in dict: ask LLM but with strict "don't guess"
            if llm.is_ready():
                answer, dbg2 = llm.chat(text=f"User asks: '{text}'. If you are not 100% sure, say you don't know.", lang=lang)
                print("CHAT:", dbg2)
                skills.tts.say(answer)
                continue

        # --- LLM fallback: ONLY chat ---
        if intent == Intent.UNKNOWN and llm.is_ready():
            if looks_like_garbage(text):
                skills.tts.say(get_prompt(cfg, lang, "unknown",
                                          "Не понял. Скажите: помощь.",
                                          "Түсінбедім. Айтыңыз: көмек."))
                continue

            answer, dbg2 = llm.chat(text=text, lang=lang)
            print("CHAT:", dbg2)
            skills.tts.say(answer)
            continue

        skills.tts.say(get_prompt(cfg, lang, "unknown",
                                  "Не понял. Скажите: помощь.",
                                  "Түсінбедім. Айтыңыз: көмек."))
    reminders.stop()

if __name__ == "__main__":
    main()