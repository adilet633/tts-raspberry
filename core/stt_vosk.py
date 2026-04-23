import json
import os
import queue
import time

from vosk import Model, KaldiRecognizer

from core.audio_in import AudioInput


class VoskSTT:
    """
    Offline Speech-to-Text using Vosk.
    Loads acoustic model from a folder path.
    """

    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.sample_rate = int(sample_rate)
        self.audio = AudioInput(sample_rate=self.sample_rate)
        self.model = None
        self.rec = None
        self.model_path = None
        self.load_model(model_path)

    def load_model(self, model_path: str) -> None:
        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                "Vosk model folder not found: {} (expected am/conf/graph/ivector inside)".format(model_path)
            )
        self.model_path = model_path
        self.model = Model(model_path)
        self.rec = KaldiRecognizer(self.model, self.sample_rate)

    def _drain_queue(self) -> None:
        while True:
            try:
                self.audio.q.get_nowait()
            except queue.Empty:
                break

    def listen_text(self, seconds: int = 6, queue_timeout: float = 0.5) -> str:
        seconds = max(1, int(seconds))
        self.rec.Reset()
        self._drain_queue()
        final_text = ""

        with self.audio.open_stream():
            end_time = time.time() + seconds
            while time.time() < end_time:
                try:
                    data = self.audio.q.get(timeout=queue_timeout)
                except queue.Empty:
                    continue

                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result() or "{}")
                    txt = res.get("text", "")
                    if txt:
                        final_text = txt

            res = json.loads(self.rec.FinalResult() or "{}")
            txt = res.get("text", "")
            if txt:
                final_text = txt

        return (final_text or "").strip().lower()