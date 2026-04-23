import os
import io
from datetime import datetime

import pyperclip

from core.tts_base import TTSBase
from core.reminders import ReminderManager
from core.sos_telegram import TelegramSOS
from core.utils import today_date_str


def _ru_num_0_59(n: int) -> str:
    ones = [
        "ноль", "один", "два", "три", "четыре", "пять",
        "шесть", "семь", "восемь", "девять"
    ]
    teens = {
        10: "десять", 11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
        14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать",
        17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать"
    }
    tens = {
        2: "двадцать",
        3: "тридцать",
        4: "сорок",
        5: "пятьдесят"
    }

    n = int(n)
    if 0 <= n <= 9:
        return ones[n]
    if 10 <= n <= 19:
        return teens[n]
    t = n // 10
    u = n % 10
    if u == 0:
        return tens.get(t, str(n))
    return f"{tens.get(t, str(t*10))} {ones[u]}"


def _ru_time_phrase(dt: datetime) -> str:
    """
    Gives a Silero-friendly phrase without ':' so it won't truncate.
    Example: "Сейчас четырнадцать ноль пять."
    """
    h = dt.hour
    m = dt.minute

    # hours 0-23 -> words; minutes 0-59 -> words
    h_words = _ru_num_0_59(h)  # ok for 0-23
    if m < 10:
        # "ноль пять" sounds clearer than just "пять"
        m_words = f"ноль {_ru_num_0_59(m)}"
    else:
        m_words = _ru_num_0_59(m)

    return f"Сейчас {h_words} {m_words}."


class Skills:
    """
    High-level assistant actions (assistive needs):
    - Time/Date
    - Reminders
    - SOS (Telegram + local alarm speech)
    - Read clipboard text aloud
    - Voice notes -> file
    """

    def __init__(
        self,
        tts: TTSBase,
        reminders: ReminderManager,
        notes_file: str,
        sos_cfg: dict,
        lang: str,
    ):
        self.tts = tts
        self.reminders = reminders
        self.notes_file = notes_file

        self.sos_cfg = sos_cfg or {}
        self.tg = None
        self.lang = lang

        if self.sos_cfg.get("telegram_enabled"):
            token = self.sos_cfg.get("telegram_bot_token", "")
            chat_id = self.sos_cfg.get("telegram_chat_id", "")
            if token and chat_id:
                self.tg = TelegramSOS(token, chat_id)

    def _say_by_lang(self, ru_text: str, kz_text: str) -> None:
        if self.lang == "kz":
            self.tts.say(kz_text)
        else:
            self.tts.say(ru_text)

    def do_time(self) -> None:
        # Safer than "HH:MM" for Silero
        self.tts.say(_ru_time_phrase(datetime.now()))

    def do_date(self) -> None:
        # Keep original format but add clear phrase
        self.tts.say(f"Сегодня {today_date_str()}.")

    def do_help(self) -> None:
        self.tts.say(
            "Я умею: время, дата, напомни через 10 минут ... , "
            "прочитай текст (из буфера), запиши заметку ..., помощь, выход, SOS."
        )

    def do_reminder(self, minutes: int, text: str) -> None:
        self.reminders.add_in_minutes(minutes, text)

        text = (text or "").strip()

        if text:
            self.tts.say(f"Хорошо, напомню {text} через {minutes} минут.")
        else:
            self.tts.say(f"Хорошо, напомню через {minutes} минут.")

    def do_read_clipboard(self) -> None:
        try:
            text = pyperclip.paste() or ""
            text = text.strip()
            if not text:
                self.tts.say("Буфер обмена пуст.")
                return
            self.tts.say(text)
        except Exception as e:
            print("[Clipboard error]", e)
            self.tts.say("Не удалось прочитать буфер обмена.")

    def do_note(self, text: str) -> None:
        text = (text or "").strip()

        if not text:
            self._say_by_lang(
                "Не понял, что нужно запомнить.",
                "Нені есте сақтау керек екенін түсінбедім."
            )
            return

        try:
            with open(self.notes_file, "a", encoding="utf-8") as f:
                f.write(text + "\n")

            if self.lang == "kz":
                self.tts.say(f"Жақсы, мен мынаны есте сақтадым: {text}.")
            else:
                self.tts.say(f"Хорошо, я запомнил: {text}.")
        except Exception as e:
            print("[Note error]", e)
            self._say_by_lang(
                "Не удалось сохранить заметку.",
                "Жазбаны сақтау мүмкін болмады."
            )

    def do_contact_relative(self) -> None:
        self._say_by_lang(
            "Связываюсь с родственниками.",
            "Туыстарыңызбен байланысып жатырмын."
        )

        if self.tg:
            msg = self.sos_cfg.get("relative_message") or "Пользователь просит связаться с родственниками."
            ok = self.tg.send(msg)

            if ok:
                self._say_by_lang(
                    "Сообщение родственникам отправлено.",
                    "Туыстарыңызға хабарлама жіберілді."
                )
            else:
                self._say_by_lang(
                    "Не удалось отправить сообщение родственникам.",
                    "Туыстарыңызға хабарлама жіберу мүмкін болмады."
                )
        else:
            self._say_by_lang(
                "Связь с родственниками не настроена.",
                "Туыстармен байланыс бапталмаған."
            )

    def do_memory_read(self) -> None:
        try:
            if not os.path.exists(self.notes_file):
                self._say_by_lang(
                    "Заметок пока нет.",
                    "Әзірге жазбалар жоқ."
                )
                return

            with open(self.notes_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            if not lines:
                self._say_by_lang(
                    "Заметок пока нет.",
                    "Әзірге жазбалар жоқ."
                )
                return

            last_notes = lines[-3:]
            text = ". ".join(last_notes)

            if self.lang == "kz":
                self.tts.say(f"Соңғы жазбалар: {text}.")
            else:
                self.tts.say(f"Последние заметки: {text}.")
        except Exception as e:
            print("[Memory read error]", e)
            self._say_by_lang(
                "Не удалось прочитать заметки.",
                "Жазбаларды оқу мүмкін болмады."
            )

    def do_sos(self) -> None:
        self._say_by_lang(
            "Экстренный режим активирован.",
            "Төтенше режим іске қосылды."
        )

        if self.sos_cfg.get("local_alarm", True):
            alarm_text = self.sos_cfg.get("speak_alarm_text")
            if not alarm_text:
                alarm_text = "Көмек керек! SOS іске қосылды!" if self.lang == "kz" else "Нужна помощь! SOS активирован!"
            self.tts.say(alarm_text)

        if self.tg:
            msg = self.sos_cfg.get("telegram_message") or "SOS! Нужна помощь."
            ok = self.tg.send(msg)

            if ok:
                self._say_by_lang(
                    "Сообщение о помощи отправлено.",
                    "Көмек туралы хабарлама жіберілді."
                )
            else:
                self._say_by_lang(
                    "Не удалось отправить сообщение о помощи.",
                    "Көмек туралы хабарламаны жіберу мүмкін болмады."
                )
        else:
            self._say_by_lang(
                "Отправка сообщения не настроена.",
                "Хабарлама жіберу бапталмаған."
            )