"""
Core package for the voice assistant.
Provides speech, TTS, reminders and SOS functionality.
"""

from .tts_base import TTSBase
from .reminders import ReminderManager
from .sos_telegram import TelegramSOS
from .stt_vosk import VoskSTT

__all__ = [
    "TTSBase",
    "ReminderManager",
    "TelegramSOS",
    "VoskSTT",
]