from abc import ABC, abstractmethod


class TTSBase(ABC):
    @abstractmethod
    def say(self, text: str) -> None:
        raise NotImplementedError

    def beep(self) -> None:
        pass