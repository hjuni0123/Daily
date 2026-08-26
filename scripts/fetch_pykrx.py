#!/usr/bin/env python3
"""
pykrx로 코스피/코스닥 시황 및 등락률 상위 종목을 가져와
render_report.py가 쓸 데이터 JSON의 '뼈대'를 만든다. 차트 PNG도 같이 만든다.

**이 스크립트는 KRX 데이터 서버(data.krx.co.kr) 접근이 필요하다.** 이 저장소가
개발된 Claude Code Remote 샌드박스에서는 접속이 막혀 있어 실행할 수 없다 — 방화벽
제약이 없는 사용자의 로컬 PC/사내 서버에서만 쓸 수 있다 (그래서 이 스크립트는 그
환경에서 실행되는지 검증하지 못했다. 처음 돌려볼 때 pykrx 쪽 컬럼명 등에서 한 번
정도 디버깅이 필요할 수 있다).

가져올 수 있는 것: 코스피/코스닥 지수, 등락률 상위/하위 종목, 최근 거래일 추이 차트.
가져올 수 없는 것(정성적 판단 필요): 이슈 종목이 "왜" 움직였는지, 지속성 판단,
캘린더, 지점 대응 요약, SIGNAL/KEY/STEP — 이 스크립트가 만든 JSON에는 TODO로
남아있으니 직접 채우거나 scripts/local_pipeline.py --with-claude 흐름을 참고할 것.

사용법:
    python3 scripts/fetch_pykrx.py --out data/2026-08-24.json
    python3 scripts/fetch_pykrx.py --date 20260824 --out data/2026-08-24.json
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

try:
    from pykrx import stock
except ImportError:
    print("pip install pykrx 필요", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chart  # noqa: E402


def find_last_trading_day(base: datetime.date) -> str:
    for i in range(10):
        d = base - datetime.timedelta(days=i)
        ds = d.strftime("%Y%m%d")
        df = stock.get_index_ohlcv_by_date(ds, ds, "1001")
        if not df.empty:
            return ds
    raise RuntimeError("최근 10일 내 영업일을 찾지 못했습니다.")


def index_indicator(ds: str, ticker: str, label: str, note: str) -> dict:
    d = datetime.datetime.strptime(ds, "%Y%m%d").date()
    start = (d - datetime.timedelta(days=14)).strftime("%Y%m%d")
    df = stock.get_index_ohlcv_by_date(start, ds, ticker)
    if len(df) < 2:
        raise RuntimeError(f"{ticker} 지수 데이터가 부족합니다 (직전 종가 계산 불가).")
    today_row, prev_row = df.iloc[-1], df.iloc[-2]
    close, prev_close = today_row["종가"], prev_row["종가"]
    change_pt = close - prev_close
    change_pct = change_pt / prev_close * 100
    return {
        "label": label,
        "open": f"{today_row['시가']:,.2f}" if "시가" in today_row else "-",
        "day_high": f"{today_row['고가']:,.2f}" if "고가" in today_row else "-",
        "close": f"{close:,.2f}",
        "change_pct": f"{change_pct:+.2f}",
        "note": f"{note} (전일비 {change_pt:+,.2f}, {change_pct:+.2f}%)",
    }


def sector_snapshot(ds: str) -> list:
    """KRX 업종지수로 업종별 등락률 + 상장시가총액 비중을 시도해본다.
    (KOSPI 200 산업분류 등 색인 체계가 pykrx 버전에 따라 다를 수 있어 실패하면
    빈 리스트를 반환한다 — 이 경우 sectors는 직접 채워야 한다.)
    """
    sectors = []
    try:
        tickers = stock.get_index_ticker_list(ds, market="KOSPI")
        for t in tickers:
            name = stock.get_index_ticker_name(t)
            df = stock.get_index_ohlcv_by_date(ds, ds, t)
            if df.empty:
                continue
            row = df.iloc[0]
            change_pct = row.get("등락률")
            cap = row.get("상장시가총액", row.get("거래대금"))
            if change_pct is None or cap is None:
                continue
            sectors.append({"name": name, "bucket": f"{change_pct:+.2f}%", "weight": float(cap), "detail": ""})
    except Exception as e:  # pykrx 업종 API는 버전/환경별로 편차가 커서 실패를 허용한다
        print(f"경고: 업종 데이터 조회 실패({e}) — sectors는 빈 채로 둡니다.", file=sys.stderr)
    return sectors


def top_movers(ds: str, n: int = 4) -> list:
    """등락률 상위(급상승/급하락) 후보를 "금일 체크포인트" 표의 초안(섹터/관심종목)으로
    쓴다. "오늘의 관점"·"근거"는 판단이 필요해 TODO로 남기고 fill_with_claude.py가 채운다."""
    df = stock.get_market_price_change(ds, ds, market="ALL")
    if "시가총액" in df.columns:
        df = df[df["시가총액"] > 3000 * 1e8]
    gainers = df.sort_values("등락률", ascending=False).head(n // 2 + n % 2)
    losers = df.sort_values("등락률", ascending=True).head(n // 2)
    out = []
    for ticker, row in list(gainers.iterrows()) + list(losers.iterrows()):
        name = row.get("종목명", ticker)
        out.append({
            "sector": "TODO",
            "stocks": f"{name}({ticker}, {row['등락률']:+.2f}%)",
            "view": "TODO",
            "rationale": "TODO: 왜 움직였는지, 오늘의 관점과 근거를 직접 채우기 (뉴스/사내 정보 기준)",
        })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="YYYYMMDD, 미지정시 최근 영업일")
    parser.add_argument("--out", required=True, help="출력 JSON 경로")
    parser.add_argument("--chart-out", help="차트 PNG 경로 (미지정시 JSON과 같은 위치)")
    args = parser.parse_args()

    ds = args.date or find_last_trading_day(datetime.date.today())
    iso_date = f"{ds[:4]}-{ds[4:6]}-{ds[6:]}"

    kospi = index_indicator(ds, "1001", "KOSPI", "TODO: 왜 이렇게 움직였는지 한 줄")
    kosdaq = index_indicator(ds, "2001", "KOSDAQ", "TODO: 왜 이렇게 움직였는지 한 줄")

    out_path = Path(args.out)
    chart_path = Path(args.chart_out) if args.chart_out else out_path.with_suffix(".chart.png")
    try:
        labels, kospi_vals, kosdaq_vals = build_chart.fetch_from_pykrx(ds, days=10)
        build_chart.build(labels, kospi_vals, kosdaq_vals, "최근 10거래일 종가 추이", chart_path)
        chart_png_path = str(chart_path)
    except Exception as e:
        print(f"경고: 차트 생성 실패({e})", file=sys.stderr)
        chart_png_path = None

    data = {
        "_note": "fetch_pykrx.py로 자동 수집. TODO 표시된 정성적 필드(title/lead/checkpoints의"
                 " sector·view·rationale/calendar)는 직접 채우거나 Claude에게 뉴스 조사를 시켜서 채울 것.",
        "date": iso_date,
        "branch_name": "인천프리미어지점",
        "department": "인턴",
        "author": "김형준",
        "contact": "khj1227@hygood.co.kr",
        "title": "TODO: 오늘 시장을 관통하는 한 문장",
        "lead": "TODO: 오늘 시황을 요약하는 1~3문장",
        "indicators": [
            kospi, kosdaq,
            {"label": "원/달러 환율", "open": "-", "day_high": "-", "close": "-", "note": "TODO (pykrx로는 못 가져옴)"},
            {"label": "WTI 원유", "open": "-", "day_high": "-", "close": "-", "note": "TODO (pykrx로는 못 가져옴)"},
            {"label": "필라델피아 반도체", "open": "-", "day_high": "-", "close": "-", "note": "TODO (pykrx로는 못 가져옴)"},
        ],
        "flows_note": "TODO: 수급 요약 한 줄",
        "flows_source": "자료: 한국거래소, 언론 보도.",
        "sectors": sector_snapshot(ds),
        "sector_analysis": "TODO: 업종 동향 분석 한 문단",
        "checkpoints": top_movers(ds),
        "calendar": [],
        "notes": "특이사항 없음",
    }
    if chart_png_path:
        data["chart_png_path"] = chart_png_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {out_path}")
    print("TODO로 남은 정성적 필드(제목/이슈종목 이유/캘린더/업종 top_stock)를 채운 뒤")
    print(f"  python3 scripts/render_report.py {out_path}")
    print("을 실행하세요.")


if __name__ == "__main__":
    main()
