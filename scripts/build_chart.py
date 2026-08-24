#!/usr/bin/env python3
"""
코스피/코스닥 최근 N거래일 종가 추이 차트를 PNG로 만든다.

pykrx로 실제 과거 시세를 가져와 그리는 게 기본 경로다 (KRX 접근이 막힌 네트워크
에서는 실패한다 — docs/AUTOMATION_GUIDE.md 참고). --kospi/--kosdaq 옵션으로
"날짜,종가" CSV 문자열을 직접 넘기면 pykrx 없이도(예: 뉴스에서 조사한 수치로)
차트를 만들 수 있다.

사용법:
    python3 scripts/build_chart.py --date 20260824 --out reports/chart_2026-08-24.png
    python3 scripts/build_chart.py --out out.png \
        --kospi "08/18,6820.1;08/19,6830.5;08/20,6850.2;08/21,6912.95;08/24,6690.62" \
        --kosdaq "08/18,845.2;08/19,840.1;08/20,838.0;08/21,812.40;08/24,809.28"
"""
import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

ROOT = Path(__file__).resolve().parent.parent
FONT_CANDIDATES = [
    ROOT / "templates" / "assets" / "fonts" / "KoPubWorld-Dotum-Pro-Bold.woff2",  # 폰트 자체는 못 씀(ttf 아님), 참고용
]

HY_DEEP = "#2D2864"
HY_MID = "#754BE4"
INK_SOFT = "#58536A"
GRID = "#E2DBF2"


def _set_korean_font():
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            return
    # 못 찾으면 기본 폰트로 진행 (한글이 네모(□)로 보일 수 있음 — 로그로 알림)
    print("경고: 시스템에 한글 폰트를 찾지 못했습니다. 축 라벨이 깨질 수 있습니다.", file=sys.stderr)


def fetch_from_pykrx(ds: str, days: int = 10):
    from pykrx import stock
    import datetime

    d = datetime.datetime.strptime(ds, "%Y%m%d").date()
    start = (d - datetime.timedelta(days=days * 2)).strftime("%Y%m%d")
    kospi = stock.get_index_ohlcv_by_date(start, ds, "1001").tail(days)
    kosdaq = stock.get_index_ohlcv_by_date(start, ds, "2001").tail(days)
    labels = [d.strftime("%m/%d") for d in kospi.index]
    return labels, list(kospi["종가"]), list(kosdaq["종가"])


def parse_series(spec: str):
    labels, values = [], []
    for point in spec.split(";"):
        label, value = point.split(",")
        labels.append(label.strip())
        values.append(float(value))
    return labels, values


def build(labels, kospi_vals, kosdaq_vals, title: str, out_path: Path):
    _set_korean_font()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 2.4), dpi=150)

    for ax, vals, name, color in (
        (ax1, kospi_vals, "KOSPI", HY_DEEP),
        (ax2, kosdaq_vals, "KOSDAQ", HY_MID),
    ):
        ax.plot(labels, vals, color=color, linewidth=2, marker="o", markersize=3)
        ax.fill_between(range(len(labels)), vals, min(vals) * 0.995, color=color, alpha=0.08)
        last_up = vals[-1] >= vals[-2] if len(vals) > 1 else True
        ax.scatter([labels[-1]], [vals[-1]], color=("#D6273C" if last_up else "#1D4ED8"), zorder=5, s=28)
        ax.set_title(f"{name}  {vals[-1]:,.2f}", fontsize=11, color="#1B1626", loc="left", fontweight="bold")
        ax.grid(axis="y", color=GRID, linewidth=0.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(axis="both", labelsize=8, color=GRID, labelcolor=INK_SOFT)
        ax.margins(x=0.05)

    fig.suptitle(title, fontsize=9, color=INK_SOFT, x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="YYYYMMDD, pykrx로 직접 가져올 때 기준일")
    parser.add_argument("--days", type=int, default=10, help="pykrx 조회 시 최근 며칠치")
    parser.add_argument("--kospi", help="'날짜,종가;날짜,종가;...' 형태로 직접 지정 (pykrx 대신)")
    parser.add_argument("--kosdaq", help="'날짜,종가;날짜,종가;...' 형태로 직접 지정 (pykrx 대신)")
    parser.add_argument("--out", required=True, help="출력 PNG 경로")
    args = parser.parse_args()

    if args.kospi and args.kosdaq:
        labels, kospi_vals = parse_series(args.kospi)
        _, kosdaq_vals = parse_series(args.kosdaq)
    elif args.date:
        labels, kospi_vals, kosdaq_vals = fetch_from_pykrx(args.date, args.days)
    else:
        print("--date(pykrx) 또는 --kospi/--kosdaq(직접 지정) 중 하나는 필요합니다.", file=sys.stderr)
        sys.exit(1)

    build(labels, kospi_vals, kosdaq_vals, f"최근 {len(labels)}거래일 종가 추이", Path(args.out))
    print(f"생성 완료: {args.out}")


if __name__ == "__main__":
    main()
