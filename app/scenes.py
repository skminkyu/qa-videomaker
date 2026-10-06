"""장면(scene) 템플릿 정의와 자동 검수 규칙."""
import re

ICONS = ["question", "warning", "x_mark", "check", "info", "search", "thermometer",
         "shield", "shield_crack", "hospital", "pharmacy", "money", "calendar", "people",
         "phone", "megaphone", "home", "document", "heart", "leaf", "car", "chart"]

# 템플릿별 필수 필드와 설명 (Claude 프롬프트와 화면 편집기에서 함께 사용)
TEMPLATES = {
    "hook": {"required": ["headline"], "desc": "첫 장면. 큰 질문형 문구 + 아이콘(icon). 시청자의 관심을 끈다."},
    "counter": {"required": ["headline", "value", "unit"],
                "desc": "핵심 숫자 하나를 크게 카운트업. value(숫자), unit(단위), subline(보조 설명)."},
    "bar": {"required": ["headline", "items"],
            "desc": "비율·수치 비교 막대그래프. items=[{label, value}] 2~5개, value는 % 또는 같은 단위 숫자. unit 선택(기본 %)."},
    "reasons": {"required": ["headline", "items"],
                "desc": "이유·주의사항 목록. items=[{icon, text}] 2~4개, text는 15자 내외."},
    "icon_message": {"required": ["headline"], "desc": "아이콘 + 핵심 메시지 한 개. icon, subline 선택."},
    "flow": {"required": ["headline", "steps"],
             "desc": "절차·순서. steps=[{icon, label}] 2~4개, label은 10자 내외."},
    "cta": {"required": ["headline"],
            "desc": "마지막 장면. 확인 방법·문의처 안내. url 또는 phone, subline 선택."},
}

MAX_LINE_CHARS = 34


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _numbers(s: str):
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s or "")
    return re.findall(r"\d+(?:\.\d+)?", s)


def estimate_seconds(narration: str) -> float:
    """TTS 없이 추정하는 낭독 길이 (한국어 약 7.5음절/초)."""
    n = len(_norm(narration))
    return max(2.5, n / 7.5 + 0.6)


def check_scene(scene: dict, source_text: str) -> list:
    """한 장면의 검수 결과 [{level, msg}] — level: error(차단) / warn(확인 필요) / info"""
    out = []
    src = _norm(source_text)
    flat = re.sub(r"(?<=\d),(?=\d{3})", "", source_text.replace(" ", ""))
    src_nums = set(_numbers(flat)) | set(re.findall(r"\d+", flat))
    t = scene.get("template")
    if t not in TEMPLATES:
        return [{"level": "error", "msg": f"알 수 없는 템플릿: {t}"}]
    for f in TEMPLATES[t]["required"]:
        if scene.get(f) in (None, "", []):
            out.append({"level": "error", "msg": f"필수 항목 누락: {f}"})
    nar = (scene.get("narration") or "").strip()
    if not nar:
        out.append({"level": "error", "msg": "내레이션이 비어 있습니다"})
    elif len(_norm(nar)) > 90:
        out.append({"level": "warn", "msg": f"내레이션이 깁니다 ({len(_norm(nar))}자) — 장면 하나는 60자 이내 권장"})
    for key in ("items", "steps"):
        if key in scene and not isinstance(scene[key], list):
            out.append({"level": "error", "msg": f"{key}는 목록이어야 합니다"})
    if t == "bar":
        for it in scene.get("items") or []:
            try:
                float(it.get("value"))
            except (TypeError, ValueError):
                out.append({"level": "error", "msg": f"막대 값이 숫자가 아닙니다: {it}"})
    if t == "counter":
        try:
            float(str(scene.get("value")).replace(",", ""))
        except ValueError:
            out.append({"level": "error", "msg": "counter의 value는 숫자여야 합니다"})

    # 사실 검증: 화면·내레이션에 나온 숫자가 원문에 있는지
    shown = " ".join(str(x) for x in [
        scene.get("headline"), scene.get("subline"), nar, scene.get("value"),
        *[f"{i.get('label', '')} {i.get('value', '')} {i.get('text', '')}" for i in scene.get("items") or [] if isinstance(i, dict)],
        *[s.get("label", "") for s in scene.get("steps") or [] if isinstance(s, dict)],
    ] if x is not None)
    missing = sorted({n for n in _numbers(shown) if n not in src_nums and n.rstrip("0").rstrip(".") not in src_nums
                      and not (len(n) == 4 and n[2:] in src_nums)})  # 2026 ↔ 26 표기
    missing = [n for n in missing if not (len(n) == 1 and n in "123456789" and n in src)]
    if missing:
        out.append({"level": "warn", "msg": "원문에서 찾지 못한 숫자: " + ", ".join(missing) + " — 사실 여부 확인"})

    refs = scene.get("source_refs") or []
    if not refs:
        out.append({"level": "warn", "msg": "근거(source_refs)가 없습니다"})
    for r in refs:
        if _norm(r) not in src:
            out.append({"level": "warn", "msg": f"근거 문장을 원문에서 찾지 못함: “{r}”"})
    if not out:
        out.append({"level": "info", "msg": "자동 검수 통과"})
    return out


def check_project(scenes: list, source_text: str, meta: dict) -> dict:
    per = [check_scene(s, source_text) for s in scenes]
    glob = []
    total = sum(estimate_seconds(s.get("narration", "")) + 0.4 for s in scenes)
    glob.append({"level": "info", "msg": f"예상 길이 약 {round(total)}초 (음성 생성 시 실제 길이로 맞춰집니다)"})
    if total > 60:
        glob.append({"level": "warn", "msg": "60초를 넘습니다 — 쇼츠는 60초 이내 권장"})
    if not 4 <= len(scenes) <= 12:
        glob.append({"level": "warn", "msg": f"장면 수 {len(scenes)}개 — 5~10개 권장"})
    if meta.get("kogl_ok") is False:
        glob.append({"level": "error", "msg": "공공누리: " + meta.get("kogl", "")})
    elif meta.get("kogl_ok") is None:
        glob.append({"level": "warn", "msg": "공공누리: " + meta.get("kogl", "확인 필요")})
    errors = sum(1 for c in glob + [c for p in per for c in p] if c["level"] == "error")
    warns = sum(1 for c in glob + [c for p in per for c in p] if c["level"] == "warn")
    return {"global": glob, "scenes": per, "errors": errors, "warnings": warns}
