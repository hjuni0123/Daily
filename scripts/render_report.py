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
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"


def trend_class(change_pt) -> str:
    try:
        v = float(str(change_pt).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return ""


def build_context(data: dict) -> dict:
    ctx = dict(data)
    for key in ("kospi", "kosdaq"):
        if key in ctx and isinstance(ctx[key], dict):
            ctx[key] = dict(ctx[key])
            ctx[key]["trend_class"] = trend_class(ctx[key].get("change_pt"))
    ctx.setdefault("branch_name", "OO지점")
    ctx.setdefault("author", "")
    ctx.setdefault("contact", "")
    ctx.setdefault("notes", "특이사항 없음")
    ctx.setdefault("issue_stocks", [])
    ctx.setdefault("checkpoints_tomorrow", [])
    ctx.setdefault("checkpoints_week", [])
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
