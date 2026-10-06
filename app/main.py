"""보도자료 → 쇼츠 웹앱 서버.

실행: uvicorn app.main:app --port 8000   (또는 ./run.sh)
"""
import json
import os
import shutil
import threading
import traceback
import uuid
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import pdf_extract, script_gen
from .render import SceneRenderer
from .scenes import ICONS, TEMPLATES, check_project
from .tts import VOICES
from .video import build_video, split_subtitles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("PROJECTS_DIR", os.path.join(ROOT, "projects"))
os.makedirs(DATA, exist_ok=True)

app = FastAPI(title="보도자료 쇼츠 메이커")
_locks: dict = {}


def _lock(pid):
    return _locks.setdefault(pid, threading.Lock())


def pdir(pid: str) -> str:
    if not pid.replace("-", "").isalnum():
        raise HTTPException(400, "잘못된 프로젝트 ID")
    d = os.path.join(DATA, pid)
    if not os.path.isdir(d):
        raise HTTPException(404, "프로젝트가 없습니다")
    return d


def load(pid: str) -> dict:
    with open(os.path.join(pdir(pid), "project.json"), encoding="utf-8") as f:
        return json.load(f)


def save(p: dict):
    path = os.path.join(DATA, p["id"], "project.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def update(pid: str, **kw):
    with _lock(pid):
        p = load(pid)
        p.update(kw)
        p["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save(p)
        return p


def source_text(pid: str) -> str:
    path = os.path.join(pdir(pid), "source.txt")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def recheck(p: dict) -> dict:
    p["checks"] = check_project(p.get("scenes") or [], source_text(p["id"]), p.get("meta") or {})
    return p


# ------------------------------------------------------------------ 백그라운드 작업

def job_script(pid: str, use_ai: bool, preset_scenes: dict = None):
    try:
        d = pdir(pid)
        update(pid, status="extracting", progress=0.1, message="PDF 텍스트 추출 중")
        r = pdf_extract.extract(os.path.join(d, "source.pdf"))
        with open(os.path.join(d, "source.txt"), "w", encoding="utf-8") as f:
            f.write(r["text"])
        update(pid, meta=r["meta"], page_count=r["page_count"], name=r["meta"]["title"] or "제목 없음")
        if preset_scenes:
            script = {"video_title": preset_scenes["meta"].get("video_title", ""), "scenes": preset_scenes["scenes"],
                      "generated_by": preset_scenes["meta"].get("generated_by", "가져온 대본")}
        else:
            ai = use_ai and script_gen.claude_available()
            update(pid, status="scripting", progress=0.4,
                   message="Claude가 대본 작성 중 (1~2분)" if ai else "규칙 기반 초안 작성 중")
            script = script_gen.generate(os.path.join(d, "source.pdf"), r["text"], r["meta"], use_ai)
        with _lock(pid):
            p = load(pid)
            p.update(status="review", progress=1.0, message="대본 검수 대기", approved=False,
                     video_title=script["video_title"], scenes=script["scenes"], generated_by=script["generated_by"])
            save(recheck(p))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        update(pid, status="error", message=f"대본 생성 실패: {e}")


def job_render(pid: str, opts: dict):
    try:
        p = load(pid)
        out = build_video(pdir(pid), p["scenes"], p["meta"], p.get("video_title", ""), opts,
                          lambda prog, msg: update(pid, progress=round(prog, 3), message=msg))
        timeline = out.pop("timeline")
        update(pid, status="done", progress=1.0, outputs={**out, "rendered_at": datetime.now().isoformat(timespec="seconds")},
               timeline=[{"start": t["start"], "dur": t["dur"]} for t in timeline],
               message=f"완료 · {out['duration']:.1f}초 · 음성: {out['tts']}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        update(pid, status="error", message=f"영상 생성 실패: {e}")


def _new_project(pdf_bytes: bytes, filename: str) -> str:
    pid = datetime.now().strftime("%y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = os.path.join(DATA, pid)
    os.makedirs(d)
    with open(os.path.join(d, "source.pdf"), "wb") as f:
        f.write(pdf_bytes)
    now = datetime.now().isoformat(timespec="seconds")
    save({"id": pid, "name": filename, "filename": filename, "created_at": now, "updated_at": now,
          "status": "queued", "progress": 0, "message": "대기 중", "meta": {}, "scenes": [], "approved": False,
          "outputs": None})
    return pid


# ------------------------------------------------------------------ API

@app.get("/api/config")
def config():
    return {"claude": script_gen.claude_available(), "model": script_gen.MODEL, "voices": VOICES,
            "templates": {k: v["desc"] for k, v in TEMPLATES.items()}, "icons": ICONS}


@app.get("/api/projects")
def list_projects():
    out = []
    for pid in sorted(os.listdir(DATA), reverse=True):
        try:
            p = load(pid)
        except Exception:  # noqa: BLE001
            continue
        out.append({k: p.get(k) for k in ("id", "name", "status", "progress", "message", "created_at",
                                           "approved", "video_title", "outputs")} | {"meta": p.get("meta", {})})
    return out


@app.post("/api/projects")
async def create_project(pdf: UploadFile = File(...), use_ai: bool = Form(True)):
    data = await pdf.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "PDF 파일이 아닙니다")
    pid = _new_project(data, pdf.filename or "보도자료.pdf")
    threading.Thread(target=job_script, args=(pid, use_ai), daemon=True).start()
    return {"id": pid}


@app.post("/api/projects/sample")
def create_sample():
    s = os.path.join(ROOT, "samples", "glp1")
    with open(os.path.join(s, "press_release.pdf"), "rb") as f:
        pid = _new_project(f.read(), "예시_식약처_GLP-1_비만치료제.pdf")
    with open(os.path.join(s, "scenes.json"), encoding="utf-8") as f:
        preset = json.load(f)
    threading.Thread(target=job_script, args=(pid, False, preset), daemon=True).start()
    return {"id": pid}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    p = load(pid)
    p["source_text"] = source_text(pid)
    return p


class ScenesIn(BaseModel):
    scenes: list
    video_title: str | None = None
    approve: bool = False


@app.put("/api/projects/{pid}/scenes")
def put_scenes(pid: str, body: ScenesIn):
    with _lock(pid):
        p = load(pid)
        if p["status"] in ("rendering", "extracting", "scripting"):
            raise HTTPException(409, "작업 중에는 수정할 수 없습니다")
        p["scenes"] = [{**s, "id": i} for i, s in enumerate(body.scenes, 1)]
        if body.video_title is not None:
            p["video_title"] = body.video_title
        recheck(p)
        if body.approve and p["checks"]["errors"]:
            p["approved"] = False
            save(p)
            raise HTTPException(422, f"차단 오류 {p['checks']['errors']}건을 먼저 고쳐 주세요")
        p["approved"] = body.approve
        p["approved_at"] = datetime.now().isoformat(timespec="seconds") if body.approve else None
        p["status"] = "approved" if body.approve else "review"
        p["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save(p)
    return p


@app.post("/api/projects/{pid}/regenerate")
def regenerate(pid: str, use_ai: bool = True):
    p = load(pid)
    if p["status"] in ("rendering", "extracting", "scripting"):
        raise HTTPException(409, "이미 작업 중입니다")
    update(pid, status="queued", approved=False)
    threading.Thread(target=job_script, args=(pid, use_ai), daemon=True).start()
    return {"ok": True}


class RenderIn(BaseModel):
    format: str = "mp4"
    tts: str = "auto"
    voice: str = "ko-KR-SunHiNeural"
    rate: str = "+8%"


@app.post("/api/projects/{pid}/render")
def render(pid: str, body: RenderIn):
    with _lock(pid):
        p = load(pid)
        if not p.get("approved"):
            raise HTTPException(409, "대본 검수·승인 후에 영상을 만들 수 있습니다")
        if p["status"] in ("rendering", "extracting", "scripting"):
            raise HTTPException(409, "이미 작업 중입니다")
        p.update(status="rendering", progress=0.01, message="영상 생성 시작", render_opts=body.model_dump())
        save(p)
    threading.Thread(target=job_render, args=(pid, body.model_dump()), daemon=True).start()
    return {"ok": True}


_renderers: dict = {}


@app.post("/api/projects/{pid}/preview")
def preview(pid: str, scene: dict, index: int = 0, total: int = 1):
    """편집 중인 장면 하나를 정지 화면 PNG로 렌더링 (저장 없이)."""
    p = load(pid)
    key = json.dumps(p.get("meta", {}), sort_keys=True, ensure_ascii=False)
    r = _renderers.get(key) or _renderers.setdefault(key, SceneRenderer(p.get("meta") or {}))
    subs = split_subtitles(scene.get("narration", ""))
    try:
        img = r.still(scene, (index + 1) / max(total, 1), subs[0] if subs else "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"미리보기 실패: {e}")
    import io
    buf = io.BytesIO()
    img.convert("RGB").resize((540, 960)).save(buf, "JPEG", quality=85)
    return Response(buf.getvalue(), media_type="image/jpeg")


FILES = {"video": None, "srt": "subtitles.srt", "txt": "subtitles.txt", "thumbnail": "thumbnail.png"}


@app.get("/api/projects/{pid}/files/{kind}")
def get_file(pid: str, kind: str, download: bool = False):
    d = pdir(pid)
    p = load(pid)
    if kind == "pdf":
        return FileResponse(os.path.join(d, "source.pdf"), media_type="application/pdf")
    if kind == "scenes":
        body = {"meta": {**p.get("meta", {}), "video_title": p.get("video_title"), "generated_by": p.get("generated_by")},
                "approved": p.get("approved"), "scenes": p.get("scenes")}
        return Response(json.dumps(body, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=scenes.json"})
    out = p.get("outputs") or {}
    if kind not in FILES or not out.get(kind):
        raise HTTPException(404, "아직 생성되지 않았습니다")
    path = os.path.join(d, "out", out[kind])
    if not os.path.exists(path):
        raise HTTPException(404, "파일이 없습니다")
    base = (p.get("video_title") or "shorts").replace("/", "_").replace(" ", "_")[:40]
    name = f"{base}{os.path.splitext(path)[1]}" if kind == "video" else f"{base}_{out[kind]}"
    return FileResponse(path, filename=name if download else None,
                        headers={"Cache-Control": "no-cache"},
                        content_disposition_type="attachment" if download else "inline")


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    d = pdir(pid)
    if load(pid)["status"] == "rendering":
        raise HTTPException(409, "렌더링 중에는 삭제할 수 없습니다")
    shutil.rmtree(d)
    return {"ok": True}


def _recover():
    """서버 재시작으로 중단된 작업 표시."""
    for pid in os.listdir(DATA):
        try:
            p = load(pid)
            if p["status"] in ("queued", "extracting", "scripting", "rendering"):
                update(pid, status="error", message="서버 재시작으로 작업이 중단되었습니다 — 다시 실행해 주세요")
        except Exception:  # noqa: BLE001
            pass


_recover()
app.mount("/fonts", StaticFiles(directory=os.path.join(ROOT, "assets", "fonts")), name="fonts")
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

