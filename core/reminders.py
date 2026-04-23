from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from core.tts_base import TTSBase


@dataclass
class Reminder:
    when: datetime
    text: str


class ReminderManager:
    def __init__(self, tts: TTSBase):
        self.tts = tts
        self.items: List[Reminder] = []

    def add_in_minutes(self, minutes: int, text: str):
        when = datetime.now() + timedelta(minutes=minutes)
        self.items.append(Reminder(when=when, text=text))
        self.items.sort(key=lambda r: r.when)

    def tick(self):
        now = datetime.now()
        fired = [r for r in self.items if r.when <= now]
        self.items = [r for r in self.items if r.when > now]

        for r in fired:
            self.tts.say(f"Напоминание: {r.text}")