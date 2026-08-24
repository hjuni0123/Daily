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
import json
import sys
from pathlib import Path

import squarify
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
ASSET_DIR = TEMPLATE_DIR / "assets"

TREEMAP_DX = 1000.0
TREEMAP_DY = 280.0


def asset_data_uri(filename: str, mime: str) -> str:
    data = (ASSET_DIR / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def logo_data_uri(filename: str) -> str:
    return asset_data_uri(filename, "image/png")


def font_data_uri(filename: str) -> str:
    return asset_data_uri(f"fonts/{filename}", "font/woff2")


def _as_float(value):
    try:
        return float(str(value).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def trend_class(change_pt) -> str:
    v = _as_float(change_pt)
    if v is None:
        return ""
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "flat"


def trend_symbol(change_pt) -> str:
    v = _as_float(change_pt)
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


def with_heat(sector: dict) -> dict:
    sector = dict(sector)
    sector["heat_class"] = heat_class(sector.get("change_pct"))
    sector.setdefault("weight", 1)
    return sector


def build_treemap(sectors: list) -> list:
    """업종 시가총액/거래대금 비중(weight)에 비례한 실제 면적의 트리맵 좌표를 계산한다."""
    if not sectors:
        return []
    ordered = sorted(sectors, key=lambda s: _as_float(s.get("weight")) or 0, reverse=True)
    weights = [max(0.001, _as_float(s.get("weight")) or 1) for s in ordered]
    normalized = squarify.normalize_sizes(weights, TREEMAP_DX, TREEMAP_DY)
    rects = squarify.squarify(normalized, 0, 0, TREEMAP_DX, TREEMAP_DY)
    out = []
    for sector, rect in zip(ordered, rects):
        sector = dict(sector)
        sector["x_pct"] = round(rect["x"] / TREEMAP_DX * 100, 3)
        sector["y_pct"] = round(rect["y"] / TREEMAP_DY * 100, 3)
        sector["w_pct"] = round(rect["dx"] / TREEMAP_DX * 100, 3)
        sector["h_pct"] = round(rect["dy"] / TREEMAP_DY * 100, 3)
        out.append(sector)
    return out


def build_context(data: dict) -> dict:
    ctx = dict(data)
    for key in ("kospi", "kosdaq"):
        if key in ctx and isinstance(ctx[key], dict):
            ctx[key] = with_trend(ctx[key])
    if "issue_stocks" in ctx:
        ctx["issue_stocks"] = [with_trend(s, "change_pct") for s in ctx["issue_stocks"]]
    if "sectors" in ctx:
        sectors = [with_heat(s) for s in ctx["sectors"]]
        ctx["sectors"] = build_treemap(sectors)
    ctx.setdefault("branch_name", "인천프리미어센터")
    ctx.setdefault("department", "인턴")
    ctx.setdefault("author", "김형준")
    ctx.setdefault("contact", "010-5912-9992")
    ctx.setdefault("notes", "특이사항 없음")
    ctx.setdefault("headline", "")
    ctx.setdefault("market_summary_prose", "")
    ctx.setdefault("sector_prose", "")
    ctx.setdefault("sectors", [])
    ctx.setdefault("issue_stocks", [])
    checkpoints = ctx.setdefault("checkpoints", [])
    for i, cp in enumerate(checkpoints):
        cp["nearest"] = (i == 0)
    ctx["logo_full_color"] = logo_data_uri("hy_logo_full_color.png")
    ctx["logo_full_white"] = logo_data_uri("hy_logo_full_white.png")
    ctx["logo_compact"] = logo_data_uri("hy_logo_compact_color.png")
    ctx["font_bold"] = font_data_uri("KoPubWorld-Dotum-Bold.woff2")
    ctx["font_medium"] = font_data_uri("KoPubWorld-Dotum-Medium.woff2")
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
