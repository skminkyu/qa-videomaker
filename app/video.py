"""장면 + 음성 + 자막 → 쇼츠 영상(mp4/avi), 자막 txt/srt."""
import os
import re
import shutil
import subprocess

from .render import SceneRenderer, W, H
from .scenes import estimate_seconds
from .tts import DEFAULT_VOICE, synth

FPS = 30
LEAD, TAIL = 0.25, 0.45   # 장면 시작 전 여백, 내레이션 뒤 여백 (초)
SUB_MAX = 34              # 자막 한 덩어리 최대 글자 수 (두 줄)


def split_subtitles(narration: str) -> list:
    """내레이션을 화면 자막 단위로 나눈다 (문장 → 너무 길면 쉼표/띄어쓰기에서)."""
    text = re.sub(r"\s+", " ", narration).strip()
    sents = [s.strip() for s in re.split(r"(?<=[.?!。])\s+", text) if s.strip()]
    out = []

    def cut(s):
        if len(s) <= SUB_MAX:
            out.append(s)
            return
        mid = len(s) / 2
        cands = [m.end() for m in re.finditer(r",\s|·|\s", s)]
        commas = [m.end() for m in re.finditer(r",\s", s)]
        pool = [c for c in commas if len(s) * 0.25 < c < len(s) * 0.8] or cands
        k = min(pool, key=lambda c: abs(c - mid)) if pool else int(mid)
        cut(s[:k].strip())
        cut(s[k:].strip())

    for s in sents:
        cut(s)
    return out


def _weight(s: str) -> float:
    return len(re.sub(r"\s", "", s)) + 2.0 * len(re.findall(r"[,.?!]", s))


def plan_timeline(scenes: list, audio_durs: list) -> list:
    """장면별 시작·길이와 자막 타이밍을 계산한다."""
    timeline, t0 = [], 0.0
    for sc, ad in zip(scenes, audio_durs):
        speech = ad if ad else estimate_seconds(sc.get("narration", "")) - 0.6
        dur = max(2.5, LEAD + speech + TAIL)
        chunks = split_subtitles(sc.get("narration", ""))
        total_w = sum(_weight(c) for c in chunks) or 1
        subs, ct = [], t0 + LEAD
        for c in chunks:
            d = speech * _weight(c) / total_w
            subs.append({"start": ct, "end": ct + d, "text": c})
            ct += d
        if subs:  # 마지막 자막은 장면 끝까지 유지
            subs[-1]["end"] = t0 + dur - 0.05
        timeline.append({"start": t0, "dur": dur, "subs": subs})
        t0 += dur
    return timeline


def _ts(t: float, sep=","):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _mmss(t: float):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def write_subtitles(timeline: list, scenes: list, meta: dict, video_title: str, srt_path: str, txt_path: str):
    n = 1
    with open(srt_path, "w", encoding="utf-8") as f:
        for tl in timeline:
            for sb in tl["subs"]:
                f.write(f"{n}\n{_ts(sb['start'])} --> {_ts(sb['end'])}\n{sb['text']}\n\n")
                n += 1
    total = timeline[-1]["start"] + timeline[-1]["dur"] if timeline else 0
    lines = [f"[{video_title}]",
             f"출처: {meta.get('agency', '')} 보도자료 ({meta.get('release_date', '')}) — {meta.get('title', '')}",
             f"영상 길이: {_mmss(total)}  ·  장면 {len(scenes)}개  ·  자막 {n - 1}줄", "",
             "■ 화면 자막 (시간순)"]
    for i, (tl, sc) in enumerate(zip(timeline, scenes), 1):
        lines.append(f"\n[장면 {i} · {sc.get('template')}]  {_mmss(tl['start'])} ~ {_mmss(tl['start'] + tl['dur'])}")
        for sb in tl["subs"]:
            lines.append(f"{_mmss(sb['start'])} ~ {_mmss(sb['end'])}  {sb['text']}")
    lines += ["", "■ 전체 내레이션", ""]
    lines += [sc.get("narration", "").strip() for sc in scenes]
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 오류: {r.stderr[-800:]}")


def build_audio(work: str, timeline: list, audio_files: list) -> str:
    parts = []
    for i, (tl, af) in enumerate(zip(timeline, audio_files)):
        out = os.path.join(work, f"a{i:02d}.wav")
        d = f"{tl['dur']:.3f}"
        if af:
            ms = int(LEAD * 1000)
            _run(["ffmpeg", "-y", "-v", "error", "-i", af, "-af", f"adelay={ms}|{ms},apad",
                  "-t", d, "-ar", "44100", "-ac", "2", out])
        else:
            _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", d, out])
        parts.append(out)
    lst = os.path.join(work, "concat.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
    full = os.path.join(work, "narration.wav")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", full])
    return full


def build_video(project_dir: str, scenes: list, meta: dict, video_title: str, opts: dict = None,
                progress=lambda p, msg: None) -> dict:
    opts = opts or {}
    fmt = opts.get("format", "mp4")
    out_dir = os.path.join(project_dir, "out")
    work = os.path.join(project_dir, "work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    # 1) 음성
    engine = opts.get("tts", "auto")
    audio_files, audio_durs, used, errs = [], [], set(), []
    for i, sc in enumerate(scenes):
        progress(0.02 + 0.18 * i / len(scenes), f"음성 생성 중 ({i + 1}/{len(scenes)})")
        mp3 = os.path.join(work, f"n{i:02d}.mp3")
        name, dur, e = synth(sc.get("narration", ""), mp3, engine, opts.get("voice", DEFAULT_VOICE),
                             opts.get("rate", "+8%")) if engine != "silent" else ("silent", None, [])
        errs += e
        used.add(name)
        audio_files.append(mp3 if dur else None)
        audio_durs.append(dur)

    timeline = plan_timeline(scenes, audio_durs)
    total = timeline[-1]["start"] + timeline[-1]["dur"]
    progress(0.2, "오디오 트랙 합성 중")
    wav = build_audio(work, timeline, audio_files)

    # 2) 영상 프레임 → ffmpeg
    ext = "avi" if fmt == "avi" else "mp4"
    video_path = os.path.join(out_dir, f"shorts.{ext}")
    for old in ("shorts.mp4", "shorts.avi"):
        if os.path.exists(os.path.join(out_dir, old)):
            os.remove(os.path.join(out_dir, old))
    venc = (["-c:v", "mpeg4", "-q:v", "2", "-c:a", "pcm_s16le"] if ext == "avi" else
            ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"])
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav, *venc, "-shortest", video_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    r = SceneRenderer(meta)
    n_frames = int(round(total * FPS))
    si = 0
    try:
        for fi in range(n_frames):
            t = fi / FPS
            while si + 1 < len(timeline) and t >= timeline[si + 1]["start"]:
                si += 1
            tl = timeline[si]
            lt = t - tl["start"]
            sub = next((s["text"] for s in tl["subs"] if s["start"] <= t < s["end"]), "")
            proc.stdin.write(r.frame(si, scenes[si], lt, t / total, sub).convert("RGB").tobytes())
            if fi % 15 == 0:
                progress(0.22 + 0.75 * fi / n_frames, f"영상 렌더링 중 ({fi}/{n_frames} 프레임)")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg 인코딩 실패: {err[-800:]}")

    # 3) 자막 파일·썸네일
    progress(0.98, "자막 파일 저장 중")
    srt = os.path.join(out_dir, "subtitles.srt")
    txt = os.path.join(out_dir, "subtitles.txt")
    write_subtitles(timeline, scenes, meta, video_title, srt, txt)
    thumb = os.path.join(out_dir, "thumbnail.png")
    r.still(scenes[0], 0.0, timeline[0]["subs"][0]["text"] if timeline[0]["subs"] else "").convert("RGB").save(thumb)
    shutil.rmtree(work, ignore_errors=True)
    tts_used = ", ".join(sorted(used))
    return {"video": os.path.basename(video_path), "srt": "subtitles.srt", "txt": "subtitles.txt",
            "thumbnail": "thumbnail.png", "duration": round(total, 2), "tts": tts_used,
            "tts_errors": sorted(set(errs)), "timeline": timeline}
