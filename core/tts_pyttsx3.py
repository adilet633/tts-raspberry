import pyttsx3
from core.tts_base import TTSBase


class Pyttsx3TTS(TTSBase):
    """
    Offline TTS for desktop (Windows/macOS/Linux).
    On Raspberry Pi can work but often less stable than espeak.
    """
    def __init__(self, rate: int = 170):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)

    def say(self, text: str) -> None:
        print(f"ASSISTANT: {text}")
        self.engine.say(text)
        self.engine.runAndWait()