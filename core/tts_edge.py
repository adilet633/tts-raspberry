import asyncio
import os
import sys
import tempfile

from core.tts_base import TTSBase


class EdgeTTSTTS(TTSBase):
    """
    Edge Neural TTS (online). Иногда может отдавать 403.
    Этот класс сделан безопасным: если Edge недоступен, он НЕ ломает приложение,
    а автоматически делает fallback на macOS say (если запущено на macOS),
    либо просто печатает текст (как последний fallback).
    """

    def __init__(self, voice: str, rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume

        try:
            import edge_tts  # noqa: F401
        except Exception as e:
            raise RuntimeError("edge-tts is not installed. Run: pip install edge-tts") from e

    async def _speak_async(self, text: str) -> None:
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            out_path = f.name

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
            )
            await communicate.save(out_path)

            # Play audio
            if os.name == "posix":
                if os.system("which afplay >/dev/null 2>&1") == 0:
                    os.system(f"afplay {out_path} >/dev/null 2>&1")
                elif os.system("which mpg123 >/dev/null 2>&1") == 0:
                    os.system(f"mpg123 -q {out_path}")
                elif os.system("which ffplay >/dev/null 2>&1") == 0:
                    os.system(f"ffplay -nodisp -autoexit -loglevel quiet {out_path}")
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass

    def _fallback_macos_say(self, text: str) -> None:
        # macOS offline voice
        safe = text.replace('"', '\\"')
        os.system(f'say "{safe}" >/dev/null 2>&1')

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        try:
            try:
                asyncio.run(self._speak_async(text))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._speak_async(text))
        except Exception as e:
            # Edge sometimes returns 403 or network errors. Do NOT crash app.
            # Fallback on macOS if possible.
            if sys.platform == "darwin":
                self._fallback_macos_say(text)
                return

            # Last resort: print to console
            print("TTS fallback (Edge failed):", e)
            print("SAY:", text)