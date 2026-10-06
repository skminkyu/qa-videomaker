#!/usr/bin/env bash
# Mac: 더블클릭으로 보도자료 쇼츠 메이커 실행
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "[처음 실행] 설치를 시작합니다. 1~2분 걸립니다..."
  python3 -m venv .venv || { echo "Python 3를 찾을 수 없습니다."; read -r; exit 1; }
  .venv/bin/python -m pip install -r requirements.txt
fi
command -v ffmpeg >/dev/null || echo "[경고] ffmpeg가 없습니다. 영상을 만들려면 'brew install ffmpeg'로 설치하세요."
[ -f apikey.txt ] && export ANTHROPIC_API_KEY="$(tr -d '[:space:]' < apikey.txt)"
echo
echo "잠시 후 브라우저가 열립니다: http://localhost:8000"
echo "이 창을 닫으면 앱이 꺼집니다."
(sleep 3; open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 >/dev/null 2>&1) &
exec .venv/bin/python -m uvicorn app.main:app --port 8000
