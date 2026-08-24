#!/usr/bin/env bash
# 로컬 PC/사내 서버(크론)에서 장마감 직후 실행하는 파이프라인.
#
# 이 저장소가 만들어진 Claude Code Remote 샌드박스는 KRX 접속이 막혀 있어서
# scripts/fetch_pykrx.py 를 실행할 수 없다 — 이 스크립트는 그 제약이 없는
# 사용자의 PC/서버에서만 쓴다.
#
# 1) pykrx로 지수·등락률 상위종목·차트를 수집해 data/{날짜}.json에 뼈대를 만든다
#    (몇 초 안에 끝난다 — 여기까지가 자동)
# 2) TODO로 남은 정성적 항목(제목/SIGNAL·KEY·STEP/이슈종목 이유/캘린더/지점 대응)을
#    채우라고 알려주고 대기한다 (사람이 직접 채우는 구간 — 몇 분)
# 3) Enter를 누르면 .md/.html/.docx 세 포맷을 렌더링한다
#
# 크론 예시 (평일 15:30 KST, 즉 사용자 서버가 KST면 그대로):
#   30 15 * * 1-5 /path/to/Daily/scripts/run_local.sh --auto >> /path/to/Daily/logs/run.log 2>&1
# --auto 로 실행하면 2)단계에서 사람 입력을 기다리지 않고 TODO가 남은 채로 바로 렌더링한다
# (크론에는 대화형 입력이 없으므로). TODO 없이 완전히 채우려면 사람이 직접 실행할 것.

set -euo pipefail
cd "$(dirname "$0")/.."

DATE="${1:-$(date +%F)}"
AUTO=false
for arg in "$@"; do
  [ "$arg" = "--auto" ] && AUTO=true
done

DATA_JSON="data/${DATE}.json"

echo "[1/3] pykrx로 지수/등락률/차트 수집 중..."
python3 scripts/fetch_pykrx.py --date "$(echo "$DATE" | tr -d '-')" --out "$DATA_JSON"

if [ "$AUTO" = false ]; then
  echo ""
  echo "[2/3] ${DATA_JSON} 을 열어 TODO 항목(제목/SIGNAL·KEY·STEP/이슈종목 이유/캘린더/지점 대응)을 채운 뒤"
  read -rp "      Enter를 눌러 렌더링을 계속하세요 (Ctrl+C로 중단) ..." _
fi

echo "[3/3] .md/.html/.docx 렌더링 중..."
python3 scripts/render_report.py "$DATA_JSON"
if [ -d scripts/docx/node_modules ]; then
  :
else
  (cd scripts/docx && npm install)
fi
node scripts/docx/render_docx.js "$DATA_JSON" "reports/${DATE}_market_report.docx"

echo ""
echo "완료: reports/${DATE}_market_report.{md,html,docx}"
