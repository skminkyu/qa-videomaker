"""보도자료 PDF에서 본문 텍스트와 메타데이터(부처, 배포일, 제목 등)를 뽑아낸다."""
import re

import pymupdf

# 정부 부처·기관 이름 (본문에서 먼저 발견되는 것을 사용)
AGENCIES = [
    "기획재정부", "교육부", "과학기술정보통신부", "외교부", "통일부", "법무부", "국방부",
    "행정안전부", "국가보훈부", "문화체육관광부", "농림축산식품부", "산업통상자원부",
    "산업통상부", "보건복지부", "환경부", "기후에너지환경부", "고용노동부", "성평등가족부",
    "여성가족부", "국토교통부", "해양수산부", "중소벤처기업부", "인사혁신처", "법제처",
    "식품의약품안전처", "국가데이터처", "통계청", "국세청", "관세청", "조달청", "경찰청",
    "소방청", "산림청", "기상청", "특허청", "농촌진흥청", "질병관리청", "해양경찰청",
    "재외동포청", "우주항공청", "방송미디어통신위원회", "공정거래위원회", "금융위원회",
    "국민권익위원회", "개인정보보호위원회", "원자력안전위원회", "국무조정실", "국무총리비서실",
]
SHORT_NAMES = {"식품의약품안전처": "식약처", "과학기술정보통신부": "과기정통부",
               "질병관리청": "질병청", "공정거래위원회": "공정위", "금융위원회": "금융위",
               "문화체육관광부": "문체부", "농림축산식품부": "농식품부", "행정안전부": "행안부",
               "국토교통부": "국토부", "고용노동부": "고용부", "중소벤처기업부": "중기부"}

KOGL_TYPES = {
    "제1유형": "공공누리 제1유형 (출처표시) — 상업적 이용·변경 가능",
    "제2유형": "공공누리 제2유형 (출처표시+상업적 이용금지)",
    "제3유형": "공공누리 제3유형 (출처표시+변경금지) — 영상화(변경) 불가",
    "제4유형": "공공누리 제4유형 (출처표시+상업적 이용금지+변경금지) — 영상화(변경) 불가",
}


def _clean(s: str) -> str:
    s = s.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def extract(pdf_path: str) -> dict:
    doc = pymupdf.open(pdf_path)
    pages = []
    for page in doc:
        lines = [_clean(l) for l in page.get_text("text").splitlines()]
        pages.append("\n".join(l for l in lines if l))
    text = "\n".join(pages)

    # 제목: 첫 페이지에서 가장 큰 글자 크기의 연속된 줄 (+ 바로 앞 줄이 제목 일부인 경우 포함)
    title = ""
    lines = []
    if doc.page_count:
        for b in doc[0].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = _clean("".join(s["text"] for s in l["spans"]))
                if t:
                    lines.append((max(s["size"] for s in l["spans"]), t))
    if lines:
        big = max(sz for sz, _ in lines)
        idx = [i for i, (sz, _) in enumerate(lines) if sz >= big * 0.9]
        if idx:
            i0, i1 = idx[0], idx[0]
            while i1 + 1 < len(lines) and lines[i1 + 1][0] >= big * 0.9:
                i1 += 1
            # 제목 첫 줄이 작은 폰트 스팬으로 시작하는 경우(예: "식약처, ...")
            if i0 > 0 and not lines[i0 - 1][1].startswith("-") and re.search(r"[가-힣]{2,}", lines[i0 - 1][1]) \
                    and not re.search(r"보도|배포|\d{4}\.", lines[i0 - 1][1]):
                i0 -= 1
            title = " ".join(t for _, t in lines[i0:i1 + 1])

    # 부제(첫 페이지의 "- ..." 줄)
    first = pages[0] if pages else ""
    subtitles = []
    for l in first.splitlines()[:30]:
        m = re.match(r"^[-–ㅇ□○]\s*(.+)", l)
        if m and len(m.group(1)) > 8:
            subtitles.append(m.group(1).strip())
        if len(subtitles) >= 3:
            break

    # 부처
    agency = ""
    m = re.search(r"([가-힣]+(?:부|처|청|위원회|실))\s*\((?:장관|처장|청장|위원장|실장|차관)", text)
    if m:
        agency = m.group(1)
    if not agency:
        hits = [(text.find(a), a) for a in AGENCIES if a in text]
        if hits:
            agency = min(hits)[1]

    # 배포일
    release_date = ""
    m = re.search(r"(20\d{2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.", text)
    if m:
        release_date = f"{m.group(1)}.{int(m.group(2))}.{int(m.group(3))}."

    # 공공누리 유형: 텍스트로 표기된 경우만 판별 가능 (마크 이미지는 판별 불가)
    kogl = "자동 판별 불가 — 원문 마지막 장의 공공누리 마크를 직접 확인하세요"
    kogl_ok = None
    for k, v in KOGL_TYPES.items():
        if re.search(r"공공누리.{0,20}" + k, text.replace("\n", " ")):
            kogl, kogl_ok = v, k in ("제1유형", "제2유형")
            break

    return {
        "text": text,
        "page_count": doc.page_count,
        "meta": {
            "agency": agency,
            "agency_short": SHORT_NAMES.get(agency, agency),
            "release_date": release_date,
            "title": title,
            "subtitles": subtitles,
            "kogl": kogl,
            "kogl_ok": kogl_ok,
        },
    }


if __name__ == "__main__":
    import json
    import sys
    r = extract(sys.argv[1])
    print(json.dumps(r["meta"], ensure_ascii=False, indent=2))
