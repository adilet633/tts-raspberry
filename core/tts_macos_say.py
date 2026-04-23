import subprocess
from core.tts_base import TTSBase


class MacOSSayTTS(TTSBase):
    """Stable TTS on macOS using built-in `say` command."""

    def __init__(self, rate: int = 170, voice: str = ""):
        self.rate = int(rate)
        self.voice = (voice or "").strip()

    def say(self, text: str) -> None:
        print("ASSISTANT:", text)
        cmd = ["say"]
        if self.voice:
            cmd += ["-v", self.voice]
        cmd += ["-r", str(self.rate), text]
        subprocess.run(cmd, check=False)

    def beep(self) -> None:
        subprocess.run(["bash", "-lc", "printf '\\a'"], check=False)