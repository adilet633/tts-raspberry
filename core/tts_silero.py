import os
import sys
import shutil
import subprocess
import tempfile
import traceback
from typing import Optional, Tuple, List

import numpy as np
import  soundfile as sf

from core.tts_base import TTSBase


def _has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _play_wav(path: str) -> None:
    # Windows
    if sys.platform.startswith("win"):
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return

    # macOS
    if _has_cmd("afplay"):
        subprocess.run(["afplay", path], check=False)
        return

    # Linux / Raspberry Pi
    if _has_cmd("aplay"):
        subprocess.run(["aplay", "-q", path], check=False)
        return

    print("[TTS] Нет проигрывателя. WAV сохранён:", path)


class SileroTTS(TTSBase):
    """
    Silero neural TTS:
      - RU: language='ru'
      - KZ: language='multi' + speaker 'aigul_v2' (или любой из доступных)
    """

    def __init__(
        self,
        language: str,
        speaker: Optional[str] = None,
        sample_rate: int = 24000,
        device: str = "cpu",
        cache_dir: Optional[str] = None,
        hub_speaker: Optional[str] = None,
    ):
        self.language = language
        self.device = device
        self.sample_rate = int(sample_rate)

        if cache_dir:
            os.environ["TORCH_HOME"] = cache_dir

        self.model, self.available_speakers = self._load_model(language, hub_speaker=hub_speaker)
        self.model.to(self.device)

        if speaker and speaker in self.available_speakers:
            self.speaker = speaker
        else:
            self.speaker = self._pick_default_speaker(language, self.available_speakers)

    def _load_model(self, language: str, hub_speaker: Optional[str] = None) -> Tuple[object, List[str]]:
        import torch

        if hub_speaker:
            load_speaker = hub_speaker
        else:
            load_speaker = "v3_1_ru" if language == "ru" else "multi_v2"

        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language=language,
            speaker=load_speaker,
            trust_repo=True,
        )

        speakers = []
        try:
            speakers = list(getattr(model, "speakers"))
        except Exception:
            speakers = []

        return model, speakers

    @staticmethod
    def _pick_default_speaker(language: str, speakers: List[str]) -> str:
        if not speakers:
            return ""

        if language == "ru":
            for pref in ["baya_v2", "kseniya_v2", "irina_v2", "natasha_v2", "aidar_v2"]:
                if pref in speakers:
                    return pref
            return speakers[0]

        for pref in ["aigul_v2", "dilyara_v2", "erdni_v2", "ruslan_v2", "aidar_v2", "baya_v2"]:
            if pref in speakers:
                return pref
        return speakers[0]

    def list_voices(self) -> List[str]:
        return list(self.available_speakers)

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        if not self.speaker:
            print("[SileroTTS] Нет speaker. TEXT:", text)
            return

        wav_path = None
        try:
            audio = self.model.apply_tts(
                text=text,
                speaker=self.speaker,
                sample_rate=self.sample_rate,
            )

            try:
                import torch
                if isinstance(audio, torch.Tensor):
                    audio_np = audio.detach().cpu().numpy().astype(np.float32)
                else:
                    audio_np = np.array(audio, dtype=np.float32)
            except Exception:
                audio_np = np.array(audio, dtype=np.float32)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            sf.write(wav_path, audio_np, self.sample_rate)
            _play_wav(wav_path)

        except Exception as e:
            print("[SileroTTS ERROR]", e)
            traceback.print_exc()
            print("[SileroTTS fallback TEXT]", text)

        finally:
            try:
                if wav_path and os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception:
                pass


class SileroRuTTS(SileroTTS):
    def __init__(self, speaker: Optional[str], sample_rate: int, device: str, cache_dir: Optional[str]):
        super().__init__(
            language="ru",
            speaker=speaker,
            sample_rate=sample_rate,
            device=device,
            cache_dir=cache_dir,
            hub_speaker="v3_1_ru",
        )


class SileroKzTTS(SileroTTS):
    def __init__(self, speaker: Optional[str], sample_rate: int, device: str, cache_dir: Optional[str]):
        super().__init__(
            language="multi",
            speaker=speaker,
            sample_rate=sample_rate,
            device=device,
            cache_dir=cache_dir,
            hub_speaker="multi_v2",
        )
