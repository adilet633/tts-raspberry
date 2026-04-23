import os
import sys
import wave
import shutil
import subprocess
import tempfile
import traceback
from typing import Optional

from core.tts_base import TTSBase


def _has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _play_wav(path: str) -> None:
    if sys.platform.startswith("win"):
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return

    if _has_cmd("afplay"):
        subprocess.run(["afplay", path], check=False)
        return

    if _has_cmd("aplay"):
        subprocess.run(["aplay", "-q", path], check=False)
        return

    if _has_cmd("ffplay"):
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path], check=False)
        return

    print("[PiperTTS] No player found. WAV saved:", path)


class PiperTTS(TTSBase):
    """
    Offline neural TTS using Piper.
    Requires:
        pip install piper-tts

    Model file example:
        models/piper/ru_RU-irina-medium.onnx
        models/piper/kk_KZ-issai-high.onnx

    Config file must be near model:
        ru_RU-irina-medium.onnx.json
    """

    def __init__(self, model_path: str):
        self.model_path = model_path

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Piper model not found: {self.model_path}")

        config_path = self.model_path + ".json"
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Piper config not found: {config_path}")

        from piper import PiperVoice

        self.voice = PiperVoice.load(self.model_path)

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        print(f"ASSISTANT: {text}")

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            with wave.open(wav_path, "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file)

            _play_wav(wav_path)

        except Exception as e:
            print("[PiperTTS ERROR]", e)
            traceback.print_exc()
            print("[PiperTTS fallback TEXT]", text)

        finally:
            try:
                if wav_path and os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception:
                pass

    def beep(self) -> None:
        subprocess.run(["bash", "-lc", "printf '\\a'"], check=False)