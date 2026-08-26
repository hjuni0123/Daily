#!/usr/bin/env python3
"""
데일리 마켓 브리핑 렌더러.

입력: JSON 데이터 파일 (스키마는 docs/AUTOMATION_GUIDE.md 참고)
출력: reports/{date}_market_report.md, reports/{date}_market_report.html

사용법:
    python3 scripts/render_report.py path/to/data.json
    python3 scripts/render_report.py path/to/data.json --outdir reports
"""
import argparse
import base64
import datetime
import json
import re
import sys
from pathlib import Path

import squarify
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
ASSET_DIR = TEMPLATE_DIR / "assets"

TREEMAP_DX = 1000.0
TREEMAP_DY = 300.0
# templates/daily_report_template.html.j2 의 .heatmap { height: ... } 와 맞춰야 한다.
HEATMAP_CSS_HEIGHT_PX = 260
COMPACT_BOX_THRESHOLD_PX = 40


def asset_data_uri(filename: str, mime: str) -> str:
    data = (ASSET_DIR / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def logo_data_uri(filename: str) -> str:
    return asset_data_uri(filename, "image/png")


def font_data_uri(filename: str) -> str:
    return asset_data_uri(f"fonts/{filename}", "font/woff2")


def _as_float(value):
    try:
        s = str(value).replace(",", "").replace("+", "").replace("bp", "").replace("%", "")
        s = s.replace("−", "-")  # 유니코드 마이너스(−) -> ASCII 하이픈
        return float(s)
    except (TypeError, ValueError):
        return None


def trend_class(value) -> str:
    v = _as_float(value)
    if v is None:
        return ""
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "flat"


def trend_symbol(value) -> str:
    v = _as_float(value)
    if v is None:
        return ""
    if v > 0:
        return "▲"
    if v < 0:
        return "▼"
    return "-"


def with_trend(d: dict, field: str = "change_pt") -> dict:
    d = dict(d)
    d["trend_class"] = trend_class(d.get(field))
    d["trend_symbol"] = trend_symbol(d.get(field))
    return d


def with_indicator_trend(i: dict) -> dict:
    """종가(close) 칸의 색상 판단 기준.

    - close 자체가 등락률(%)인 지표(WTI/필라델피아 반도체 등, 해외 지표라
      가격 대신 등락률만 표기)는 close를 그대로 부호 판단에 쓴다.
    - close가 실제 가격/지수값인 지표(코스피/코스닥/원달러 등)는 가격의
      부호가 항상 양수라 그대로 쓰면 늘 "상승"으로 잘못 칠해진다 — 별도
      change_pct(전일대비 등락률, 화면에는 표시하지 않는 내부용 필드)가
      있으면 그걸로 판단하고, 없으면(예: "HTS 확인") 색을 매기지 않는다.
    """
    i = dict(i)
    basis = i["change_pct"] if i.get("change_pct") not in (None, "") else i.get("close")
    i["trend_class"] = trend_class(basis)
    i["trend_symbol"] = trend_symbol(basis)
    return i


def heat_class(change_pct) -> str:
    v = _as_float(change_pct)
    if v is None:
        return "heat-flat"
    if v >= 3:
        return "heat-up-3"
    if v >= 1.5:
        return "heat-up-2"
    if v > 0:
        return "heat-up-1"
    if v == 0:
        return "heat-flat"
    if v > -1.5:
        return "heat-down-1"
    if v > -3:
        return "heat-down-2"
    return "heat-down-3"


def bucket_heat_class(bucket) -> str:
    """업종 방향성이 정확한 등락률(%) 대신 '강보합'/'+1%대'/'약보합' 같은 버킷
    라벨로 주어질 때 색상 클래스를 매긴다."""
    b = str(bucket or "").strip()
    if "상한가" in b or "급등" in b:
        return "heat-up-3"
    if "하한가" in b or "급락" in b:
        return "heat-down-3"
    m = re.search(r"\+([0-9.]+)", b)
    if m:
        return "heat-up-2" if float(m.group(1)) >= 2 else "heat-up-1"
    m = re.search(r"[−\-]([0-9.]+)", b)
    if m:
        return "heat-down-2" if float(m.group(1)) >= 2 else "heat-down-1"
    if "강보합" in b:
        return "heat-up-1"
    if "약보합" in b:
        return "heat-down-1"
    return "heat-flat"


def with_heat(sector: dict) -> dict:
    sector = dict(sector)
    if "bucket" in sector:
        sector["heat_class"] = bucket_heat_class(sector.get("bucket"))
    else:
        sector["heat_class"] = heat_class(sector.get("change_pct"))
    sector.setdefault("weight", 1)
    return sector


def build_treemap(sectors: list) -> list:
    """업종 시가총액 비중(weight)에 비례한 실제 면적의 트리맵 좌표를 계산한다."""
    if not sectors:
        return []
    ordered = sorted(sectors, key=lambda s: _as_float(s.get("weight")) or 0, reverse=True)
    weights = [max(0.001, _as_float(s.get("weight")) or 1) for s in ordered]
    total = sum(weights)
    normalized = squarify.normalize_sizes(weights, TREEMAP_DX, TREEMAP_DY)
    rects = squarify.squarify(normalized, 0, 0, TREEMAP_DX, TREEMAP_DY)
    out = []
    for sector, rect, w in zip(ordered, rects, weights):
        sector = dict(sector)
        sector["x_pct"] = round(rect["x"] / TREEMAP_DX * 100, 3)
        sector["y_pct"] = round(rect["y"] / TREEMAP_DY * 100, 3)
        sector["w_pct"] = round(rect["dx"] / TREEMAP_DX * 100, 3)
        sector["h_pct"] = round(rect["dy"] / TREEMAP_DY * 100, 3)
        sector["weight_pct"] = round(w / total * 100, 1)
        box_px = sector["h_pct"] / 100 * HEATMAP_CSS_HEIGHT_PX
        sector["compact"] = box_px < COMPACT_BOX_THRESHOLD_PX
        out.append(sector)
    return out


WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def build_context(data: dict) -> dict:
    ctx = dict(data)

    if "indicators" in ctx:
        ctx["indicators"] = [with_indicator_trend(i) for i in ctx["indicators"]]
    if "sectors" in ctx:
        ctx["sectors"] = build_treemap([with_heat(s) for s in ctx["sectors"]])
    ctx.setdefault("calendar", [])
    ctx.setdefault("checkpoints", [])

    ctx.setdefault("branch_name", "인천프리미어지점")
    # 참고: 한양증권 공식 점포 안내상 명칭은 "인천프리미어센터"이나, 사용자 제공
    # 레퍼런스 문서에서 일관되게 "인천프리미어지점"으로 표기되어 있어 이를 따랐다.
    ctx.setdefault("department", "인턴")
    ctx.setdefault("author", "김형준")
    ctx.setdefault("contact", "khj1227@hygood.co.kr")
    ctx.setdefault("title", "")
    ctx.setdefault("lead", "")
    ctx.setdefault("indicators", [])
    ctx.setdefault("sectors", [])
    ctx.setdefault("sector_analysis", "")
    ctx.setdefault("flows_note", "")
    ctx.setdefault("flows_source", "")
    ctx.setdefault("notes", "특이사항 없음")

    if "date" in ctx:
        y, m, d = ctx["date"].split("-")
        ctx["date_short"] = f"{int(m)}/{int(d)}"
        dow = WEEKDAY_KO[datetime.date(int(y), int(m), int(d)).weekday()]
        ctx["date_full"] = f"{int(y)}년 {int(m)}월 {int(d)}일({dow})"

    ctx["logo_full_color"] = logo_data_uri("hy_logo_full_color.png")
    ctx["logo_full_white"] = logo_data_uri("hy_logo_full_white.png")
    ctx["logo_compact"] = logo_data_uri("hy_logo_compact_color.png")
    ctx["font_bold"] = font_data_uri("KoPubWorld-Dotum-Pro-Bold.woff2")
    ctx["font_light"] = font_data_uri("KoPubWorld-Dotum-Pro-Light.woff2")
    return ctx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_file", help="리포트 데이터 JSON 파일 경로")
    parser.add_argument("--outdir", default=str(ROOT / "reports"), help="출력 디렉터리")
    args = parser.parse_args()

    data_path = Path(args.data_file)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    if "date" not in data:
        print("data JSON에 'date' 필드(YYYY-MM-DD)가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    ctx = build_context(data)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{data['date']}_market_report"

    md = env.get_template("daily_report_template.md.j2").render(**ctx)
    (outdir / f"{stem}.md").write_text(md, encoding="utf-8")

    html = env.get_template("daily_report_template.html.j2").render(**ctx)
    (outdir / f"{stem}.html").write_text(html, encoding="utf-8")

    print(f"생성 완료:\n  {outdir / f'{stem}.md'}\n  {outdir / f'{stem}.html'}")


if __name__ == "__main__":
    main()
