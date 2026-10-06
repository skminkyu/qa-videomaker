# 보도자료 → 쇼츠 메이커 (qa-videomaker)

정부 부처 **보도자료 PDF**를 올리면 아래 결과물을 만드는 웹앱입니다.

| 결과물 | 파일 | 내용 |
|---|---|---|
| 결과물 1 | `shorts.mp4` 또는 `shorts.avi` | 1080×1920 세로 쇼츠 영상 (30fps, 내레이션 음성 + 자막 + 애니메이션 그래픽) |
| 결과물 2 | `subtitles.txt` | 영상에 들어간 자막 전체 (시간순 타임코드 + 전체 내레이션) |
| 부가 | `subtitles.srt`, `thumbnail.png`, `scenes.json` | 유튜브 업로드용 자막, 썸네일, 검수된 대본 |
| 3 | 웹앱 (`http://localhost:8000`) | 1·2를 프로젝트 단위로 통합 관리 (업로드 → 검수 → 승인 → 생성 → 다운로드) |

## 실행

필요: Python 3.10+, **ffmpeg**

```bash
./run.sh                 # 의존성 설치 후 http://localhost:8000 실행
# 또는
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Claude가 대본을 쓰게 하려면 API 키를 설정합니다 (없으면 규칙 기반 초안을 만들고, 사람이 검수 화면에서 고칩니다).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export CLAUDE_MODEL=claude-opus-5-5   # 선택 (기본값)
```

## 작업 흐름

1. **PDF 업로드** — 여러 개를 한 번에 끌어다 놓을 수 있습니다. 부처·배포일·제목·부제·공공누리 표기를 자동 추출합니다.
2. **대본 자동 작성** — Claude가 PDF 원문만 근거로 6~9개 장면(hook → 숫자/그래프/이유/절차 → 안내)을 작성하고, 장면마다 근거 문장(`source_refs`)을 답니다.
3. **검수** (`① 대본 검수` 탭)
   - 장면별 미리보기 이미지가 편집 즉시 갱신됩니다.
   - 근거를 클릭하면 오른쪽 원문에서 해당 위치가 강조됩니다.
   - 자동 검수: 원문에 없는 숫자, 원문에서 찾을 수 없는 근거, 긴 내레이션, 필수 항목 누락, 60초 초과, 공공누리 유형.
   - 장면 추가·삭제·순서 변경, 템플릿 변경, JSON 직접 편집.
4. **승인** — 차단 오류가 없어야 승인됩니다. 승인된 대본만 영상으로 만들 수 있습니다.
5. **영상 생성** (`② 영상 · 자막` 탭) — 형식(MP4/AVI), 음성 엔진, 목소리, 속도를 고르고 생성. 완료되면 플레이어·자막 텍스트·다운로드 버튼이 나타납니다.

예시: 왼쪽 「예시 프로젝트 열기」를 누르면 식약처 GLP-1 비만치료제 보도자료(`samples/glp1`)와 검수된 예시 대본이 열립니다.

## 장면 템플릿

| 템플릿 | 용도 | 주요 필드 |
|---|---|---|
| `hook` | 첫 장면 질문 | `icon`, `headline` |
| `counter` | 핵심 숫자 카운트업 | `value`, `unit`, `subline` |
| `bar` | 비율·건수 막대그래프 | `items: [{label, value}]`, `unit`(기본 %) |
| `reasons` | 이유·주의사항 목록 | `items: [{icon, text}]` |
| `icon_message` | 한 가지 메시지 | `icon`, `headline`, `subline` |
| `flow` | 절차 | `steps: [{icon, label}]` |
| `cta` | 확인 방법·문의처 | `url` 또는 `phone`, `subline` |

`headline`에서 `\n`은 줄바꿈, `**단어**`는 강조색입니다. 모든 장면에는 `narration`(음성·자막)과 `source_refs`(원문 근거)가 있습니다.

## 음성 (TTS)

`자동`은 edge-tts(Microsoft 신경망 한국어 음성) → gTTS → 무음 순으로 시도합니다. 둘 다 인터넷 연결이 필요하며, 실패하면 자막만 있는 무음 영상이 만들어지고 결과 화면에 실패 원인이 표시됩니다. 장면 길이와 자막 타이밍은 실제 음성 길이에 맞춰집니다.

## 명령줄

```bash
python -m app.cli 보도자료.pdf -o 결과폴더                       # 대본 자동 작성 + 영상
python -m app.cli 보도자료.pdf -o 결과폴더 --scenes scenes.json   # 웹앱에서 검수한 대본으로
python -m app.cli 보도자료.pdf -o 결과폴더 --format avi --tts silent
```

## 구조

```
app/
  main.py         FastAPI 서버 (프로젝트·작업 관리 API, 정적 파일)
  pdf_extract.py  PDF 텍스트·메타데이터 추출 (PyMuPDF)
  script_gen.py   대본 생성 (Claude API 구조화 출력 / 규칙 기반 초안)
  scenes.py       템플릿 정의, 자동 검수 규칙
  render.py       장면 그래픽 렌더링 (Pillow, 1080×1920)
  icons.py        벡터 아이콘
  tts.py          음성 합성
  video.py        타임라인·자막 분할, ffmpeg 인코딩, txt/srt 작성
  cli.py          명령줄 실행
  static/index.html  관리 웹앱 (단일 페이지)
assets/fonts/     Pretendard (SIL OFL 1.1)
samples/glp1/     예시 보도자료와 예시 대본
projects/         생성된 프로젝트 저장소 (git 제외)
```

## 주의

- 공공누리 유형은 PDF 안의 텍스트로 표기된 경우만 자동 판별합니다. 마크 이미지만 있으면 「자동 판별 불가」로 표시되니 원문 마지막 장을 직접 확인하세요 (제3·4유형은 변경 금지라 영상화할 수 없습니다).
- 자동 검수는 보조 수단입니다. 공개 전 사람이 원문과 대조해 승인하세요.
