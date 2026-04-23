import subprocess
from core.tts_base import TTSBase


class EspeakTTS(TTSBase):
    """
    Offline TTS using espeak-ng (best for Raspberry Pi).
    Requires: sudo apt-get install espeak-ng
    """
    def __init__(self, voice: str = "ru", rate: int = 170):
        self.voice = voice
        self.rate = rate

    def say(self, text: str) -> None:
        print(f"ASSISTANT: {text}")
        # -s speed, -v voice
        cmd = ["espeak-ng", "-v", self.voice, "-s", str(self.rate), text]
        subprocess.run(cmd, check=False)

    def beep(self) -> None:
        # A short beep tone (optional)
        subprocess.run(["bash", "-lc", "printf '\\a'"], check=False)