from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from threading import Thread, Event, Lock
import time

from core.tts_base import TTSBase


def _build_reminder_phrase(text: str) -> str:
    text = (text or "").strip().lower()

    if not text:
        return "Напоминание."

    if "лекар" in text or "таблет" in text:
        return f"Напоминание. Пора {text}."

    if "воду" in text or "вода" in text:
        return f"Напоминание. Пора {text}."

    if "поесть" in text or "покушать" in text or "обед" in text or "ужин" in text or "завтрак" in text:
        return f"Напоминание. Пора {text}."

    if "спать" in text or "отдохнуть" in text:
        return f"Напоминание. Пора {text}."

    return f"Напоминание: {text}."


@dataclass
class Reminder:
    when: datetime
    text: str


class ReminderManager:
    def __init__(self, tts: TTSBase):
        self.tts = tts
        self.items: List[Reminder] = []
        self._stop_event = Event()
        self._lock = Lock()
        self._thread = Thread(target=self._worker, daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def add_in_minutes(self, minutes: int, text: str):
        if minutes < 1:
            minutes = 1

        when = datetime.now() + timedelta(minutes=minutes)

        with self._lock:
            self.items.append(Reminder(when=when, text=text))
            self.items.sort(key=lambda r: r.when)

    def tick(self):
        # можно оставить для совместимости, но теперь основная работа идет в фоне
        self._check_and_fire()

    def _check_and_fire(self):
        now = datetime.now()

        with self._lock:
            fired = [r for r in self.items if r.when <= now]
            self.items = [r for r in self.items if r.when > now]

        for r in fired:
            try:
                self.tts.say(_build_reminder_phrase(r.text))
            except Exception as e:
                print("[Reminder TTS error]", e)

    def _worker(self):
        while not self._stop_event.is_set():
            self._check_and_fire()
            time.sleep(1)