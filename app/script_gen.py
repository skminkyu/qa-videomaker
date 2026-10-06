"""보도자료 → 쇼츠 대본(장면 목록) 생성.

ANTHROPIC_API_KEY(또는 `ant auth login` 프로필)가 있으면 Claude가 대본을 쓰고,
없거나 실패하면 규칙 기반 초안을 만든다. 어느 쪽이든 사람이 검수 화면에서 고친다.
"""
import base64
import json
import os
import re

from .scenes import ICONS, TEMPLATES

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM_PROMPT = """너는 정부 보도자료를 일반 시민용 세로형 쇼츠(9:16, 30~55초) 영상 대본으로 바꾸는 작가다.

원칙
- 사실은 오직 보도자료 원문에서만 가져온다. 원문에 없는 숫자·주장·추측을 만들지 않는다.
- 내레이션은 친근한 해요체 구어. 한 장면 내레이션은 1~2문장, 60자 이내.
- 장면은 6~9개. 첫 장면은 hook(질문·궁금증 유발), 마지막 장면은 cta(확인 방법·문의처·행동 요령).
- 핵심 숫자는 counter, 비율·건수 비교는 bar, 위험·이유는 reasons, 절차는 flow, 단일 메시지는 icon_message.
- headline은 화면에 크게 들어가는 짧은 문구(줄바꿈은 \\n, 강조할 단어는 **굵게**). 한 줄 12자 이내, 3줄 이내.
- 모든 장면에 source_refs를 단다: 근거가 된 원문 구절을 원문 그대로(띄어쓰기 포함) 짧게 1~3개 인용.
- 숫자를 화면에 쓸 때는 원문 숫자를 그대로 쓴다(반올림·환산 금지).
- 담당자 이름·전화번호 같은 개인 정보는 넣지 않는다(대표 콜센터·누리집은 가능).

템플릿
""" + "\n".join(f"- {k}: {v['desc']} (필수: {', '.join(v['required'])})" for k, v in TEMPLATES.items()) + f"""

아이콘(icon) 값은 다음 중에서만 고른다: {', '.join(ICONS)}
"""

_item = {"type": "object", "properties": {
    "label": {"type": "string"}, "value": {"type": "number"}, "icon": {"type": "string", "enum": ICONS},
    "text": {"type": "string"}}, "additionalProperties": False}
SCHEMA = {
    "type": "object",
    "properties": {
        "video_title": {"type": "string", "description": "영상 제목 (20자 이내, 시청자 관점)"},
        "scenes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "enum": list(TEMPLATES)},
                "icon": {"type": "string", "enum": ICONS},
                "headline": {"type": "string"},
                "subline": {"type": "string"},
                "value": {"type": "number"},
                "unit": {"type": "string"},
                "url": {"type": "string"},
                "phone": {"type": "string"},
                "items": {"type": "array", "items": _item},
                "steps": {"type": "array", "items": _item},
                "narration": {"type": "string"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["template", "headline", "narration", "source_refs"],
            "additionalProperties": False,
        }},
    },
    "required": ["video_title", "scenes"],
    "additionalProperties": False,
}


def claude_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def _tidy(scenes: list) -> list:
    out = []
    for i, s in enumerate(scenes, 1):
        s = {k: v for k, v in s.items() if v not in (None, "", [])}
        if s.get("template") == "counter" and isinstance(s.get("value"), float) and s["value"].is_integer():
            s["value"] = int(s["value"])
        for key in ("items", "steps"):
            if key in s:
                s[key] = [{k: v for k, v in it.items() if v not in (None, "")} for it in s[key]]
        out.append({"id": i, **s})
    return out


def generate_with_claude(pdf_path: str, text: str, meta: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode()
    user = (f"부처: {meta.get('agency')}\n배포일: {meta.get('release_date')}\n제목: {meta.get('title')}\n\n"
            "첨부한 보도자료로 쇼츠 대본을 만들어 줘. 아래는 PDF에서 추출한 텍스트다. "
            "source_refs는 이 추출 텍스트에 그대로 존재하는 구절이어야 한다.\n\n"
            f"<extracted_text>\n{text}\n</extracted_text>")
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": user},
        ]}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("응답이 잘렸습니다 (max_tokens)")
    data = json.loads(next(b.text for b in msg.content if b.type == "text"))
    return {"video_title": data["video_title"], "scenes": _tidy(data["scenes"]),
            "generated_by": f"Claude API ({msg.model})"}


# ---------------------------------------------------------------- 규칙 기반 초안

def _sentences(text: str) -> list:
    flat = re.sub(r"\s*\n\s*", " ", text)
    flat = re.sub(r"-\s*\d+\s*-", " ", flat)
    parts = re.split(r"(?<=다\.)\s+|(?<=요\.)\s+", flat)
    out = []
    for p in parts:
        p = re.sub(r"^(또한|특히|한편|아울러|이와 함께),\s*", "", p.strip())
        if 15 <= len(p) <= 220 and not re.match(r"^[*※<]", p):
            out.append(p)
    return out


def _polite(s: str) -> str:
    """'~했다고 밝혔다.' 같은 보도체를 짧은 해요체로 대략 바꾼다."""
    s = re.sub(r"\([^)]*\)|\*|「|」|｢|｣|‘|’", "", s)
    s = re.sub(r"(라|다)고 (밝혔|당부했|강조했|전했)다\.?$", "다.", s)
    rules = [(r"해야 한다\.?$", "해야 해요."), (r"하였다\.?$", "했어요."), (r"했다\.?$", "했어요."),
             (r"이다\.?$", "이에요."), (r"있다\.?$", "있어요."), (r"없다\.?$", "없어요."),
             (r"어렵다\.?$", "어려워요."), (r"된다\.?$", "돼요."), (r"한다\.?$", "해요."),
             (r"않도록 다\.?$", "마세요."), (r"겠다\.?$", "겠습니다.")]
    for a, b in rules:
        if re.search(a, s):
            return re.sub(a, b, s)
    return s


def _shorten(s: str, n: int = 60, end: str = ".") -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    for sep in [", ", " 및 ", " "]:
        k = cut.rfind(sep)
        if k > n * 0.5:
            return cut[:k].rstrip(",") + end
    return cut + "…"


def _ref(s: str, n: int = 40) -> str:
    return s[:n]


def generate_rule_based(text: str, meta: dict) -> dict:
    agency = meta.get("agency_short") or meta.get("agency") or "정부"
    title = meta.get("title") or ""
    topic = re.sub(r"^[가-힣A-Za-z]+,\s*", "", title)
    flat = re.sub(r"\s*\n\s*", " ", text)
    scenes = []

    # 1) hook
    head = re.sub(r"\s*(발표|추진|시행|개최|실시)$", "", topic)
    scenes.append({"template": "hook", "icon": "question",
                   "headline": _wrap_headline(head + "?" if len(head) < 22 else head),
                   "narration": f"{agency}가 발표한 소식, 1분 안에 정리해 드릴게요.",
                   "source_refs": [_ref(title)]})

    # 2) counter: 부제/본문의 첫 '숫자+단위'
    pool = " ".join(meta.get("subtitles") or []) + " " + flat
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(건|명|억\s?원|조\s?원|만\s?원|원|개소|곳|개|%|배|톤)", pool)
    if m:
        val = m.group(1).replace(",", "")
        sub = next((s for s in meta.get("subtitles") or [] if m.group(1) in s), "")
        ctx = sub or flat[max(0, flat.find(m.group(0)) - 60): flat.find(m.group(0)) + 10]
        scenes.append({"template": "counter", "headline": _shorten(re.sub(r"\d[\d,.]*\s*\S*", "", ctx), 18, "") or "핵심 숫자",
                       "value": float(val) if "." in val else int(val), "unit": m.group(2).replace(" ", ""),
                       "subline": f"{meta.get('release_date', '')} {agency} 발표".strip(),
                       "narration": _shorten(_polite(sub + "입니다.") if sub else f"{m.group(0)}입니다.", 60),
                       "source_refs": [m.group(0)]})

    # 3) bar: "OO 123건(45.6%)" 패턴
    items = re.findall(r"([가-힣A-Za-z·\s]{2,40}?)\s*(\d[\d,]*)\s*(?:건|명|개|곳)\s*\((\d+(?:\.\d+)?)%\)", flat)
    if len(items) >= 2:
        bars = []
        for label, _, pct in items[:5]:
            label = re.sub(r"^(▲|등|및|통한|을|를)\s*", "", label.strip()).split(" ")[-3:]
            bars.append({"label": " ".join(label), "value": float(pct)})
        scenes.append({"template": "bar", "headline": "유형별로 보면?", "items": bars,
                       "narration": f"가장 많은 건 {bars[0]['label']}로, {bars[0]['value']}%를 차지했어요.",
                       "source_refs": [f"{items[0][1]}건({items[0][2]}%)"]})

    # 4) 본문 핵심 문장들 → icon_message / reasons
    sents = _sentences(text)
    risky = [s for s in sents if re.search(r"위험|우려|주의|피해|불법|금지|어렵", s)][:3]
    if risky:
        scenes.append({"template": "reasons", "headline": "왜 주의해야 할까요?",
                       "items": [{"icon": ic, "text": _shorten(_polite(r), 16, "").rstrip(".")}
                                 for ic, r in zip(["warning", "x_mark", "shield_crack"], risky)],
                       "narration": _shorten(_polite(risky[0]), 60),
                       "source_refs": [_ref(r) for r in risky]})
    used = set(risky)
    for s in sents:
        if len(scenes) >= 6:
            break
        if s in used or re.search(r"담당|책임자|붙임|\d{3}-\d{3,4}-\d{4}", s):
            continue
        used.add(s)
        scenes.append({"template": "icon_message", "icon": "info",
                       "headline": _wrap_headline(_shorten(_polite(s), 22, "").rstrip(".")),
                       "narration": _shorten(_polite(s), 60), "source_refs": [_ref(s)]})

    # 5) cta: URL 또는 대표 전화
    url = re.search(r"(?:https?://)?((?:[a-z0-9-]+\.)+(?:go\.kr|or\.kr|kr|com))", flat)
    phone = re.search(r"(\d{3,4}-\d{4}|1\d{3})\s*\)?", flat)
    cta = {"template": "cta", "icon": "search", "headline": "자세한 내용은\n여기서 확인",
           "subline": f"{agency} 보도자료 {meta.get('release_date', '')}".strip(),
           "narration": "자세한 내용은 누리집에서 확인할 수 있어요.", "source_refs": []}
    if url:
        cta["url"] = url.group(1)
        cta["source_refs"] = [url.group(1)]
    elif phone:
        cta["phone"] = phone.group(1)
        cta["source_refs"] = [phone.group(1)]
    scenes.append(cta)
    return {"video_title": _shorten(topic, 24, ""), "scenes": _tidy(scenes),
            "generated_by": "규칙 기반 초안 (API 키를 설정하면 Claude가 대본을 작성합니다)"}


def _wrap_headline(s: str, width: int = 11) -> str:
    words, lines, cur = s.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


def generate(pdf_path: str, text: str, meta: dict, use_ai: bool = True) -> dict:
    if use_ai and claude_available():
        try:
            return generate_with_claude(pdf_path, text, meta)
        except Exception as e:  # noqa: BLE001 — 실패해도 규칙 기반 초안으로 계속
            r = generate_rule_based(text, meta)
            r["generated_by"] += f" — Claude 호출 실패: {type(e).__name__}: {e}"
            return r
    return generate_rule_based(text, meta)
