import queue
import sounddevice as sd


class AudioInput:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = int(sample_rate)
        self.q = queue.Queue()

    def _callback(self, indata, frames, time_info, status):
        # status can be logged if needed
        self.q.put(bytes(indata))

    def open_stream(self):
        return sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )