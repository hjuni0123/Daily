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
업종(sectors)·국제 금·WTI 원유: 예전엔 "Toss API에 없다"고 단정하고 아예 시도조차
안 했는데, 이건 검증 없이 넘겨짚은 것이었다(토스 앱/서드파티 CLI에서 업종·테마
데이터가 실제로 보이는 걸 보면 어딘가엔 있을 가능성이 높다). 그래서 지금은
sector_indicators()/commodity_indicator()가 몇 가지 가능성 있는 엔드포인트·심볼을
실제로 "시도"해보고, 성공하면 채우고 실패하면 그 실패 원인(HTTP 상태/응답 본문)을
stderr에 그대로 찍는다 — 이 스크립트는 KRX/토스 API 접근이 막힌 샌드박스에서
작성됐기 때문에 실제로 맞는 엔드포인트인지 한 번도 검증하지 못했다. 로컬에서
처음 돌려보고 sectors가 비거나 실패 로그가 찍히면, 그 stderr 내용을 그대로
공유해주면 정확한 엔드포인트로 고칠 수 있다.
가져올 수 없는 것: 상승/하락 종목수·신용잔고 등 시장폭 일부, 이슈 종목이 "왜"
움직였는지/지속성/캘린더 — 이 스크립트가 만든 JSON에는 TODO로 남아있으니
직접 채우거나 fill_with_claude.py로 채울 것.

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
    """market-indicators candles(1d, count=2)로 시가/장중고점/종가와 전일대비를
    계산한다. open/day_high는 candle에 openPrice/highPrice 필드가 없는 심볼이면
    "-"로 남는다(가격 자체는 없어도 렌더링은 깨지지 않는다).
    change_pct는 화면에 그대로 표시되진 않고(비고에 서술로 녹여 쓰거나 Claude가
    참고), render_report.py가 종가 칸 색상(상승/하락)을 매기는 데만 쓰인다."""
    result = _get(f"/api/v1/market-indicators/{symbol}/candles", {"interval": "1d", "count": 2})
    candles = result["candles"]
    if len(candles) < 2:
        raise RuntimeError(f"{symbol} 캔들이 2개 미만 — 전일 종가 계산 불가")
    today, prev = candles[0], candles[1]
    close = float(today["closePrice"])
    prev_close = float(prev["closePrice"])
    change_pt = close - prev_close
    change_pct = change_pt / prev_close * 100
    open_px = today.get("openPrice")
    high_px = today.get("highPrice")
    return {
        "label": label,
        "open": f"{float(open_px):,.2f}" if open_px is not None else "-",
        "day_high": f"{float(high_px):,.2f}" if high_px is not None else "-",
        "close": f"{close:,.2f}",
        "change_pct": f"{change_pct:+.2f}",
        "note": f"TODO: 왜 이렇게 움직였는지 한 줄 (전일비 {change_pt:+,.2f}, {change_pct:+.2f}%)",
    }


def exchange_rate_indicator() -> dict:
    """Toss 환율 엔드포인트는 현재가만 주고 시가/고점/전일비는 없어 "-"로 둔다."""
    result = _get("/api/v1/exchange-rate", {"baseCurrency": "USD", "quoteCurrency": "KRW"})
    rate = float(result["rate"])
    return {
        "label": "원/달러 환율",
        "open": "-",
        "day_high": "-",
        "close": f"{rate:,.2f}",
        "note": "TODO (시가/전일대비는 API로 못 가져옴 — 필요하면 뉴스로 채우기)",
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


# --- 아래 두 함수는 EXPERIMENTAL이다: 이 환경에서 Toss API 서버 접근이 막혀 있어
# 실제로 맞는 경로/심볼인지 한 번도 검증하지 못했다. 실패해도 스크립트 전체가
# 죽지 않도록 각각 빈 리스트/None을 반환하고, 실패 사유를 stderr에 남긴다.

COMMODITY_CANDIDATES = {
    "WTI 원유": ["WTI", "USOIL", "CL", "WTICRUDE"],
    "필라델피아 반도체": ["SOX", "PHLX", "SOXX", "SMH"],
}


def commodity_indicator(label: str) -> dict | None:
    """국제 금/WTI를 KOSPI/KOSDAQ과 같은 market-indicators/candles 엔드포인트로
    시도해본다 — 심볼 이름만 다를 뿐 같은 엔드포인트 구조일 가능성이 있어서다.
    후보 심볼을 순서대로 시도하고, 하나라도 성공하면 어떤 심볼이 맞았는지
    stderr에 남긴다(다음부터는 그 심볼을 바로 쓰도록 코드에 반영할 것)."""
    last_err = None
    for symbol in COMMODITY_CANDIDATES.get(label, []):
        try:
            ind = index_indicator(symbol, label)
            print(f"  성공: {label} <- 심볼 '{symbol}' (이 심볼로 코드에 고정하세요)", file=sys.stderr)
            return ind
        except Exception as e:
            last_err = e
    print(f"경고: {label} 후보 심볼 {COMMODITY_CANDIDATES.get(label, [])} 모두 실패"
          f"(마지막 오류: {last_err}) — '-'로 남김. developers.tossinvest.com에서 정확한"
          f" 심볼/엔드포인트를 확인해 알려주면 코드에 반영하겠습니다.", file=sys.stderr)
    return None


SECTOR_ENDPOINT_CANDIDATES = [
    "/api/v1/sectors",
    "/api/v1/sectors/rankings",
    "/api/v1/market-indicators/sectors",
    "/api/v1/industries",
]


def sector_indicators() -> list:
    """업종별 등락률·비중을 시도해본다. 정확한 경로를 몰라 후보를 순서대로
    찔러보고, 응답 스키마도 모르니 흔한 필드명(name/change_pct 등 몇 가지 후보)을
    관대하게 시도한다. 다 실패하면 빈 리스트 — sectors 히트맵은 비게 된다."""
    for path in SECTOR_ENDPOINT_CANDIDATES:
        try:
            result = _get(path, {"marketCountry": "KR"})
        except Exception as e:
            print(f"  시도 실패: {path} ({e})", file=sys.stderr)
            continue
        items = result if isinstance(result, list) else result.get("sectors") or result.get("rankings") or []
        if not items:
            continue
        out = []
        for it in items:
            name = it.get("name") or it.get("sectorName")
            change_pct = it.get("changeRate") or it.get("changePct") or it.get("change_pct")
            weight = it.get("weight") or it.get("marketCapWeight")
            if name is None or change_pct is None:
                continue
            pct = float(change_pct) * (100 if abs(float(change_pct)) < 1 else 1)
            entry = {"name": name, "bucket": f"{pct:+.2f}%", "detail": ""}
            if weight is not None:
                entry["weight"] = float(weight)
            out.append(entry)
        if out:
            print(f"  성공: {path} 에서 업종 {len(out)}개 (이 경로로 코드에 고정하세요)", file=sys.stderr)
            return out
    print("경고: 업종(sectors) 후보 엔드포인트 모두 실패 — sectors는 빈 채로 둡니다."
          " developers.tossinvest.com 문서에서 정확한 경로/응답 스키마를 확인해"
          " 알려주면 코드에 반영하겠습니다.", file=sys.stderr)
    return []


MIN_TRADING_AMOUNT_KRW = 3_000_000_000  # 30억원 미만 거래대금은 제외 (품질 낮은 픽 방지)


def top_movers(n: int = 4) -> list:
    """등락률 상위(급상승/급하락) 후보를 "금일 체크포인트" 표의 초안(섹터/관심종목)으로
    쓴다 — 투자유의종목(관리종목·정리매매 등, 가격제한폭이 없어 ±30%를 벗어나는
    비정상적 등락이 나올 수 있음)과 거래대금이 너무 적은 종목은 제외한다.
    "오늘의 관점"·"근거"는 판단이 필요해 TODO로 남기고 fill_with_claude.py가 채운다."""
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
            "sector": "TODO",
            "stocks": f"{names.get(p['symbol'], p['symbol'])}({p['symbol']}, {change_pct:+.2f}%)",
            "view": "TODO",
            "rationale": "TODO: 왜 움직였는지, 오늘의 관점과 근거를 직접 채우기 (뉴스/사내 정보 기준)",
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

    print("금일 체크포인트 초안(등락률 상위 종목) 조회 중...", file=sys.stderr)
    checkpoints = top_movers()

    print("WTI 원유/필라델피아 반도체 조회 시도 중(EXPERIMENTAL)...", file=sys.stderr)
    wti = commodity_indicator("WTI 원유") or {
        "label": "WTI 원유", "open": "-", "day_high": "-", "close": "-",
        "note": "TODO (자동 조회 실패 — 뉴스로 채우기, 미국장 기준이라 전일 종가를 씀)",
    }
    philly = commodity_indicator("필라델피아 반도체") or {
        "label": "필라델피아 반도체", "open": "-", "day_high": "-", "close": "-",
        "note": "TODO (자동 조회 실패 — 뉴스로 채우기, 미국장 기준이라 전일 종가를 씀)",
    }

    print("업종(sectors) 조회 시도 중(EXPERIMENTAL)...", file=sys.stderr)
    sectors = sector_indicators()

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
                 "(title/lead/checkpoints의 sector·view·rationale/calendar)는 직접 채우거나"
                 " fill_with_claude.py로 채울 것. sectors/WTI/필라델피아 반도체는"
                 " EXPERIMENTAL 자동 조회를 시도했다 — 비어있거나 '-'면 stderr 로그를"
                 " 확인해 정확한 엔드포인트/심볼을 알려줄 것.",
        "date": today.isoformat(),
        "branch_name": "인천프리미어지점",
        "department": "인턴",
        "author": "김형준",
        "contact": "khj1227@hygood.co.kr",
        "title": "TODO: 오늘 시장을 관통하는 한 문장",
        "lead": "TODO: 오늘 시황을 요약하는 1~3문장",
        "indicators": [kospi, kosdaq, fx, wti, philly],
        "flows": flows,
        "flows_note": "TODO: 수급 요약 한 줄",
        "flows_source": "자료: 한국거래소, 서울외국환중개, 언론 보도.",
        "sectors": sectors,
        "sector_analysis": "TODO: 업종 동향 분석 한 문단",
        "checkpoints": checkpoints,
        "calendar": [],
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
