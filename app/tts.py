"""내레이션 음성 합성. edge-tts(Microsoft 신경망 음성) → gTTS → 무음 순으로 시도한다."""
import asyncio
import json
import os
import subprocess

VOICES = {
    "ko-KR-SunHiNeural": "선희 (여성, 밝음)",
    "ko-KR-InJoonNeural": "인준 (남성, 차분)",
    "ko-KR-HyunsuMultilingualNeural": "현수 (남성, 다국어)",
}
DEFAULT_VOICE = "ko-KR-SunHiNeural"


def probe_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def _edge(text: str, out: str, voice: str, rate: str):
    import edge_tts

    async def run():
        await edge_tts.Communicate(text, voice, rate=rate).save(out)
    asyncio.run(run())


def _gtts(text: str, out: str):
    from gtts import gTTS
    gTTS(text, lang="ko").save(out)


def synth(text: str, out_mp3: str, engine: str = "auto", voice: str = DEFAULT_VOICE, rate: str = "+8%"):
    """음성 파일을 만들고 (엔진 이름, 길이초, 오류 목록)을 돌려준다. 모두 실패하면 ('silent', None, 오류)."""
    order = {"auto": ["edge", "gtts"], "edge": ["edge"], "gtts": ["gtts"], "silent": []}[engine]
    errors = []
    for name in order:
        try:
            if os.path.exists(out_mp3):
                os.remove(out_mp3)
            if name == "edge":
                _edge(text, out_mp3, voice, rate)
            else:
                _gtts(text, out_mp3)
            if os.path.getsize(out_mp3) > 1000:
                return name, probe_duration(out_mp3), errors
        except Exception as e:  # noqa: BLE001 — 네트워크·인증서 문제 등은 다음 엔진으로
            errors.append(f"{name}: {type(e).__name__}")
    return "silent", None, errors
