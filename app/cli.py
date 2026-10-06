"""명령줄 실행: 검수 화면 없이 PDF → 영상·자막을 한 번에 만든다.

  python -m app.cli 보도자료.pdf -o 결과폴더 [--scenes scenes.json] [--tts silent] [--format avi]

자동 검수에서 차단 오류가 나오면 멈춘다. 공개 전에는 웹앱에서 사람이 검수하는 것을 권장한다.
"""
import argparse
import json
import os
import shutil
import sys

from . import pdf_extract, script_gen
from .scenes import check_project
from .video import build_video


def main():
    ap = argparse.ArgumentParser(description="보도자료 PDF → 쇼츠 영상 + 자막")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="output")
    ap.add_argument("--scenes", help="검수한 scenes.json 사용 (웹앱에서 내보낸 파일)")
    ap.add_argument("--no-ai", action="store_true", help="Claude 대신 규칙 기반 초안")
    ap.add_argument("--tts", default="auto", choices=["auto", "edge", "gtts", "silent"])
    ap.add_argument("--voice", default="ko-KR-SunHiNeural")
    ap.add_argument("--format", default="mp4", choices=["mp4", "avi"])
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    r = pdf_extract.extract(a.pdf)
    if a.scenes:
        d = json.load(open(a.scenes, encoding="utf-8"))
        script = {"video_title": d["meta"].get("video_title", ""), "scenes": d["scenes"]}
    else:
        print("대본 작성 중…", file=sys.stderr)
        script = script_gen.generate(a.pdf, r["text"], r["meta"], not a.no_ai)
        print(script["generated_by"], file=sys.stderr)
    with open(os.path.join(a.out, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": {**r["meta"], "video_title": script["video_title"]}, "scenes": script["scenes"]},
                  f, ensure_ascii=False, indent=2)
    checks = check_project(script["scenes"], r["text"], r["meta"])
    for c in checks["global"] + [dict(c, msg=f"장면 {i + 1}: {c['msg']}") for i, cs in enumerate(checks["scenes"]) for c in cs]:
        if c["level"] != "info":
            print(f"[{c['level']}] {c['msg']}", file=sys.stderr)
    if checks["errors"]:
        sys.exit("차단 오류가 있어 중단합니다 — scenes.json을 고친 뒤 --scenes 로 다시 실행하세요")
    out = build_video(a.out, script["scenes"], r["meta"], script["video_title"],
                      {"tts": a.tts, "voice": a.voice, "format": a.format},
                      lambda p, m: print(f"\r{int(p * 100):3d}% {m:<40}", end="", file=sys.stderr))
    print(file=sys.stderr)
    for k in ("video", "txt", "srt", "thumbnail"):
        src = os.path.join(a.out, "out", out[k])
        shutil.move(src, os.path.join(a.out, out[k]))
    os.rmdir(os.path.join(a.out, "out"))
    print(f"완료: {os.path.join(a.out, out['video'])} ({out['duration']}초, 음성 {out['tts']})")


if __name__ == "__main__":
    main()
