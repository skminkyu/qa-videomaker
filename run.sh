#!/usr/bin/env bash
# 보도자료 쇼츠 메이커 실행: http://localhost:8000
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg가 필요합니다 (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)"; exit 1; }
python3 -m pip install -q -r requirements.txt
exec python3 -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
