from abc import ABC, abstractmethod


class TTSBase(ABC):
    @abstractmethod
    def say(self, text: str) -> None:
        ...

    def beep(self) -> None:
        # optional
        pass