#!/usr/bin/env bash
# 로컬 PC/사내 서버(크론)에서 장마감 직후 실행하는 파이프라인.
#
# 이 저장소가 만들어진 Claude Code Remote 샌드박스는 KRX/토스/Anthropic API
# 접속이 막혀 있어서 이 스크립트를 실행할 수 없다 — 방화벽 제약이 없는 사용자의
# PC/서버에서만 쓴다.
#
# 1) .env에 TOSS_API_KEY가 있으면 fetch_toss.py(토스증권 Open API, 실시간
#    시세)를, 없으면 fetch_pykrx.py(KRX)를 써서 지수·등락률 상위종목·차트를
#    수집해 data/{날짜}.json에 뼈대를 만든다 (숫자만 채워짐 — 몇 초)
# 2) .env에 ANTHROPIC_API_KEY가 있으면 fill_with_claude.py가 웹서치로 "왜
#    이렇게 움직였는지"·캘린더·지점 대응 같은 정성적 필드를 자동으로 채운다
#    (숫자는 절대 건드리지 않는다 — 1)에서 가져온 실제 값 그대로 유지). 키가
#    없으면 사람이 TODO를 직접 채우도록 대기한다 (--auto면 그냥 TODO로 둔 채 진행)
# 3) .md/.html/.docx 세 포맷을 렌더링한다
#
# 크론 예시 (평일 15:30 KST):
#   30 15 * * 1-5 /path/to/Daily/scripts/run_local.sh --auto >> /path/to/Daily/logs/run.log 2>&1
# ANTHROPIC_API_KEY까지 .env에 있으면 --auto로 완전 무인 자동화(TODO 없이 완성)가 된다.
# 없으면 --auto는 TODO가 남은 채로 렌더링만 한다(사람이 나중에 손으로 채워야 함).

set -euo pipefail
cd "$(dirname "$0")/.."

DATE="$(date +%F)"
AUTO=false
for arg in "$@"; do
  if [ "$arg" = "--auto" ]; then
    AUTO=true
  else
    DATE="$arg"
  fi
done

DATA_JSON="data/${DATE}.json"
HAS_TOSS=false
HAS_ANTHROPIC=false
[ -f .env ] && grep -q '^TOSS_API_KEY=.\+' .env && HAS_TOSS=true
[ -f .env ] && grep -q '^ANTHROPIC_API_KEY=.\+' .env && HAS_ANTHROPIC=true

if [ "$HAS_TOSS" = true ]; then
  echo "[1/3] 토스증권 Open API로 지수/환율/수급/등락률/차트 수집 중..."
  python3 scripts/fetch_toss.py --out "$DATA_JSON"
else
  echo "[1/3] pykrx로 지수/등락률/차트 수집 중... (.env에 TOSS_API_KEY 없음)"
  python3 scripts/fetch_pykrx.py --date "$(echo "$DATE" | tr -d '-')" --out "$DATA_JSON"
fi

if [ "$HAS_ANTHROPIC" = true ]; then
  echo "[2/3] Claude(웹서치)로 제목/SIGNAL·KEY·STEP/이슈종목 이유/캘린더/지점 대응 자동 작성 중..."
  python3 scripts/fill_with_claude.py "$DATA_JSON"
elif [ "$AUTO" = false ]; then
  echo ""
  echo "[2/3] ${DATA_JSON} 을 열어 TODO 항목(제목/SIGNAL·KEY·STEP/이슈종목 이유/캘린더/지점 대응)을 채운 뒤"
  read -rp "      Enter를 눌러 렌더링을 계속하세요 (Ctrl+C로 중단) ..." _
else
  echo "[2/3] .env에 ANTHROPIC_API_KEY 없음 — TODO를 채우지 않고 그대로 진행합니다."
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
