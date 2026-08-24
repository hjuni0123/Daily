#!/usr/bin/env python3
"""
pykrx로 코스피/코스닥 시황 및 등락률 상위 종목을 가져와
render_report.py가 쓸 데이터 JSON의 '뼈대'를 만든다.

주의: KRX 데이터 서버(data.krx.co.kr) 접근이 막혀 있는 네트워크(예: 일부
샌드박스/사내망)에서는 실패한다. 그런 환경에서는 이 스크립트 대신
docs/AUTOMATION_GUIDE.md 의 절차대로 웹 검색 등으로 데이터를 조사해
JSON을 직접 채워 넣으면 된다.

사용법:
    python3 scripts/fetch_pykrx.py                 # 최근 영업일 기준
    python3 scripts/fetch_pykrx.py --date 20260821
    python3 scripts/fetch_pykrx.py --out data/2026-08-21.json
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


def find_last_trading_day(base: datetime.date) -> str:
    for i in range(10):
        d = base - datetime.timedelta(days=i)
        ds = d.strftime("%Y%m%d")
        df = stock.get_index_ohlcv_by_date(ds, ds, "1001")
        if not df.empty:
            return ds
    raise RuntimeError("최근 10일 내 영업일을 찾지 못했습니다.")


def index_summary(ds: str, ticker: str) -> dict:
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
        "close": f"{close:,.2f}",
        "change_pt": f"{change_pt:+,.2f}",
        "change_pct": f"{change_pct:+.2f}",
        "value": f"{today_row['거래대금'] / 1e8:,.0f}억원",
    }


def top_movers(ds: str, market: str, n: int = 5) -> dict:
    df = stock.get_market_price_change(ds, ds, market=market)
    df = df[df["시가총액"] > 3000 * 1e8] if "시가총액" in df.columns else df
    gainers = df.sort_values("등락률", ascending=False).head(n)
    losers = df.sort_values("등락률", ascending=True).head(n)
    stocks = []
    for ticker, row in gainers.iterrows():
        stocks.append({
            "name": row.get("종목명", ticker), "ticker": ticker,
            "change_pct": f"{row['등락률']:+.2f}", "reason": "TODO: 뉴스 조사 후 채우기",
        })
    for ticker, row in losers.iterrows():
        stocks.append({
            "name": row.get("종목명", ticker), "ticker": ticker,
            "change_pct": f"{row['등락률']:+.2f}", "reason": "TODO: 뉴스 조사 후 채우기",
        })
    return stocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="YYYYMMDD, 미지정시 최근 영업일")
    parser.add_argument("--out", help="출력 JSON 경로, 미지정시 stdout")
    args = parser.parse_args()

    ds = args.date or find_last_trading_day(datetime.date.today())
    iso_date = f"{ds[:4]}-{ds[4:6]}-{ds[6:]}"
    weekday = "월화수목금토일"[datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:])).weekday()]

    data = {
        "date": iso_date,
        "weekday": weekday,
        "branch_name": "OO지점",
        "author": "",
        "contact": "",
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kospi": index_summary(ds, "1001"),
        "kosdaq": index_summary(ds, "2001"),
        "fx": {"rate": "TODO", "change": "TODO"},
        "us": {"dow": "TODO", "sp500": "TODO", "nasdaq": "TODO"},
        "market_comment": "TODO",
        "sector_top": "TODO",
        "sector_bottom": "TODO",
        "issue_stocks": top_movers(ds, "ALL"),
        "checkpoints_tomorrow": ["TODO"],
        "checkpoints_week": ["TODO"],
        "notes": "특이사항 없음",
    }

    out_str = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_str, encoding="utf-8")
        print(f"저장 완료: {out_path}")
    else:
        print(out_str)


if __name__ == "__main__":
    main()
