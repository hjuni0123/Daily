#!/usr/bin/env python3
"""
토스증권 Open API로 코스피/코스닥 지수·환율·수급·등락률 상위 종목을 가져와
render_report.py가 쓸 데이터 JSON의 '뼈대'를 만든다. 차트 PNG도 같이 만든다.

**실제 계좌의 API 키/시크릿과 방화벽 제약 없는 네트워크가 필요하다** — 사용자의
로컬 PC(cron)에서 실행하도록 만들어졌다. 인증 방식(토큰 발급: client_id/
client_secret을 form 바디로 전달)과 각 엔드포인트는 공식 문서
(https://developers.tossinvest.com/docs)로 직접 검증했다.

가져올 수 있는 것: 코스피/코스닥 지수 종가·등락(전일대비), 원/달러 환율(현재가),
투자자별(개인/외국인/기관) 순매수 대금, 등락률·거래대금 상위 종목, 최근 거래일
추이 차트.
가져올 수 없는 것: 업종별 데이터(Toss API에 섹터 엔드포인트가 없음 — sectors는
빈 채로 남으니 pykrx나 뉴스로 채울 것), 상승/하락 종목수·신용잔고 등 시장폭
일부, 이슈 종목이 "왜" 움직였는지/지속성/캘린더/지점 대응/SIGNAL·KEY·STEP —
이 스크립트가 만든 JSON에는 TODO로 남아있으니 직접 채울 것.

사용법:
    python3 scripts/fetch_toss.py --out data/2026-08-24.json
"""
import argparse
import datetime
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chart  # noqa: E402
import toss_client  # noqa: E402

API = "https://openapi.tossinvest.com"


def _get(path: str, params: dict) -> dict:
    token = toss_client.get_access_token()
    resp = requests.get(
        f"{API}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(f"GET {path} {params} 실패: {resp.status_code} {resp.text}")
    return resp.json()["result"]


def index_indicator(symbol: str, label: str) -> dict:
    """market-indicators candles(1d, count=2)로 종가/전일비를 계산한다."""
    result = _get(f"/api/v1/market-indicators/{symbol}/candles", {"interval": "1d", "count": 2})
    candles = result["candles"]
    if len(candles) < 2:
        raise RuntimeError(f"{symbol} 캔들이 2개 미만 — 전일 종가 계산 불가")
    close = float(candles[0]["closePrice"])
    prev_close = float(candles[1]["closePrice"])
    change_pt = close - prev_close
    change_pct = change_pt / prev_close * 100
    return {
        "label": label,
        "close": f"{close:,.2f}",
        "change_pt": f"{change_pt:+,.2f}",
        "change_pct": f"{change_pct:+.2f}%",
        "note": "TODO: 왜 이렇게 움직였는지 한 줄",
    }


def exchange_rate_indicator() -> dict:
    result = _get("/api/v1/exchange-rate", {"baseCurrency": "USD", "quoteCurrency": "KRW"})
    rate = float(result["rate"])
    return {
        "label": "원/달러",
        "close": f"{rate:,.2f}",
        "change_pt": "-",
        "change_pct": "-",
        "note": "TODO (전일대비는 API로 못 가져옴 — 필요하면 뉴스로 채우기)",
    }


def _amt_krw_to_eok(buy: str, sell: str) -> float:
    return (float(buy) - float(sell)) / 1e8


def investor_flows(symbol: str) -> dict:
    result = _get(f"/api/v1/market-indicators/{symbol}/investor-trading", {"interval": "1d", "count": 1})
    records = result["records"]
    if not records:
        return {"foreign": "-", "inst": "-", "retail": "-"}
    r = records[0]
    foreign = _amt_krw_to_eok(r["foreigner"]["buyAmount"], r["foreigner"]["sellAmount"])
    inst = _amt_krw_to_eok(r["institution"]["buyAmount"], r["institution"]["sellAmount"])
    retail = _amt_krw_to_eok(r["individual"]["buyAmount"], r["individual"]["sellAmount"])
    return {
        "foreign": f"{foreign:+,.0f}",
        "inst": f"{inst:+,.0f}",
        "retail": f"{retail:+,.0f}",
    }


def stock_names(symbols: list) -> dict:
    """종목코드 -> 종목명. /api/v1/stocks 파라미터명은 문서에서 미확인이라
    실패하면 종목코드를 이름으로 대신 쓴다 (렌더링은 깨지지 않는다)."""
    if not symbols:
        return {}
    try:
        result = _get("/api/v1/stocks", {"symbols": ",".join(symbols)})
        return {s["symbol"]: s.get("name", s["symbol"]) for s in result}
    except Exception as e:
        print(f"경고: 종목명 조회 실패({e}) — 종목코드를 이름으로 대신 씁니다.", file=sys.stderr)
        return {}


MIN_TRADING_AMOUNT_KRW = 3_000_000_000  # 30억원 미만 거래대금은 제외 (품질 낮은 픽 방지)


def top_movers(n: int = 4) -> list:
    """등락률 상위(급상승/급하락) 후보를 가져오되, 투자유의종목(관리종목·정리매매 등 —
    가격제한폭이 없어 ±30%를 벗어나는 비정상적인 등락이 나올 수 있음)과 거래대금이
    너무 적은 종목은 제외한다. 여유 있게 더 뽑은 뒤 필터링해서 n개를 채운다."""
    fetch_n = max(n * 3, 10)
    gainers = _get("/api/v1/rankings", {
        "type": "TOP_GAINERS", "marketCountry": "KR", "duration": "1d",
        "count": fetch_n, "excludeInvestmentCaution": True,
    })["rankings"]
    time.sleep(0.1)
    losers = _get("/api/v1/rankings", {
        "type": "TOP_LOSERS", "marketCountry": "KR", "duration": "1d",
        "count": fetch_n, "excludeInvestmentCaution": True,
    })["rankings"]

    gainers = [r for r in gainers if int(r["tradingAmount"]) >= MIN_TRADING_AMOUNT_KRW][: n // 2 + n % 2]
    losers = [r for r in losers if int(r["tradingAmount"]) >= MIN_TRADING_AMOUNT_KRW][: n // 2]

    picks = gainers + losers
    names = stock_names([p["symbol"] for p in picks])

    out = []
    for p in picks:
        change_pct = float(p["price"]["changeRate"]) * 100
        out.append({
            "name": names.get(p["symbol"], p["symbol"]),
            "ticker": p["symbol"],
            "change_pct": f"{change_pct:+.2f}",
            "reason": "TODO: 왜 움직였는지 직접 채우기 (뉴스/사내 정보 기준)",
            "persistence": "중립",
            "checkpoint": "TODO",
        })
    return out


def chart_data(days: int = 10) -> tuple:
    kospi = _get("/api/v1/market-indicators/KOSPI/candles", {"interval": "1d", "count": days})["candles"]
    kosdaq = _get("/api/v1/market-indicators/KOSDAQ/candles", {"interval": "1d", "count": days})["candles"]
    kospi = list(reversed(kospi))  # 오래된 순으로
    kosdaq = list(reversed(kosdaq))
    labels = [c["timestamp"][5:10].replace("-", "/") for c in kospi]
    kospi_vals = [float(c["closePrice"]) for c in kospi]
    kosdaq_vals = [float(c["closePrice"]) for c in kosdaq]
    return labels, kospi_vals, kosdaq_vals


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="출력 JSON 경로")
    parser.add_argument("--chart-out", help="차트 PNG 경로 (미지정시 JSON과 같은 위치)")
    args = parser.parse_args()

    toss_client._load_env_file(ROOT / ".env")

    today = datetime.date.today()
    weekday = "월화수목금토일"[today.weekday()]

    print("코스피/코스닥 지수 조회 중...", file=sys.stderr)
    kospi = index_indicator("KOSPI", "KOSPI")
    kosdaq = index_indicator("KOSDAQ", "KOSDAQ")

    print("환율 조회 중...", file=sys.stderr)
    fx = exchange_rate_indicator()

    print("투자자별 수급 조회 중...", file=sys.stderr)
    flows = {
        "kospi": investor_flows("KOSPI"),
        "kosdaq": investor_flows("KOSDAQ"),
        "futures": "-",
    }

    print("등락률 상위 종목 조회 중...", file=sys.stderr)
    issue_stocks = top_movers()

    out_path = Path(args.out)
    chart_path = Path(args.chart_out) if args.chart_out else out_path.with_suffix(".chart.png")
    try:
        print("차트 생성 중...", file=sys.stderr)
        labels, kospi_vals, kosdaq_vals = chart_data(10)
        build_chart.build(labels, kospi_vals, kosdaq_vals, "최근 10거래일 종가 추이", chart_path)
        chart_png_path = str(chart_path)
    except Exception as e:
        print(f"경고: 차트 생성 실패({e})", file=sys.stderr)
        chart_png_path = None

    data = {
        "_note": "fetch_toss.py로 자동 수집(토스증권 Open API). TODO 표시된 정성적 필드"
                 "(이유/지속성/캘린더/SIGNAL·KEY·STEP/지점 대응)와 sectors(업종, Toss API"
                 " 미지원)는 직접 채우거나 뉴스 조사로 채울 것.",
        "date": today.isoformat(),
        "weekday": weekday,
        "branch_name": "인천프리미어지점",
        "department": "인턴",
        "author": "김형준",
        "contact": "010-5912-9992",
        "generated_at": datetime.datetime.now().strftime("%H:%M"),
        "eyebrow": "시장 마감 브리프",
        "title": "TODO: 오늘 시장을 관통하는 한 문장",
        "subtitle": "TODO",
        "signal": "TODO",
        "key_point": "TODO",
        "step": "TODO",
        "indicators": [
            kospi, kosdaq, fx,
            {"label": "미 10년물", "close": "-", "change_pt": "-", "change_pct": "-", "note": "TODO (Toss API 미지원)"},
            {"label": "S&P500 선물 / WTI", "close": "-", "change_pt": "", "change_pct": "-", "note": "TODO (Toss API 미지원)"},
        ],
        "flows": flows,
        "breadth": {"advance_decline": "-", "note": "TODO", "trading_value": "-", "margin_balance": "-"},
        "sectors": [],
        "sector_prose": "TODO",
        "issue_stocks": issue_stocks,
        "calendar": [],
        "stance": {"maintain": "TODO", "reduce": "TODO", "cash": "TODO"},
        "notes": "특이사항 없음",
    }
    if chart_png_path:
        data["chart_png_path"] = chart_png_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {out_path}")
    print("TODO로 남은 정성적 필드와 sectors를 채운 뒤")
    print(f"  python3 scripts/render_report.py {out_path}")
    print("을 실행하세요.")


if __name__ == "__main__":
    main()
