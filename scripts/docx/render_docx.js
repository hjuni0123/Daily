#!/usr/bin/env node
/**
 * 데일리 마켓 브리핑 -> .docx 렌더러.
 *
 * scripts/render_report.py 와 동일한 데이터 JSON(스키마는 docs/AUTOMATION_GUIDE.md 참고)을
 * 읽어 "시장 마감 브리프" 워드 양식으로 렌더링한다.
 *
 * 사용법:
 *   cd scripts/docx && npm install   (최초 1회)
 *   node render_docx.js ../../data/2026-08-24.json ../../reports/2026-08-24_market_report.docx
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, ImageRun,
  VerticalAlign, HeadingLevel,
} = require("docx");

const HY_DEEP = "2D2864";
const HY_MID = "754BE4";
const HY_TINT = "F5F3FA";
const HY_TINT_LINE = "E2DBF2";
const INK = "1B1626";
const INK_SOFT = "58536A";
const INK_FAINT = "8F8A9E";
const UP = "D6273C";
const DOWN = "1D4ED8";
const WHITE = "FFFFFF";

const HEAT = {
  "heat-up-3": { fill: "C81E2C", fg: WHITE },
  "heat-up-2": { fill: "E2495A", fg: WHITE },
  "heat-up-1": { fill: "F4B7BE", fg: "6B1420" },
  "heat-flat": { fill: "E9E6EF", fg: INK_SOFT },
  "heat-down-1": { fill: "B7C9F6", fg: "16306E" },
  "heat-down-2": { fill: "5C87E8", fg: WHITE },
  "heat-down-3": { fill: "1D4ED8", fg: WHITE },
};

const FONT = "맑은 고딕";
const GRID_W = 12; // 트리맵 표 전체 컬럼 수 (twip 단위 아님, 상대 비중)
const PAGE_W = 11000; // dxa, 본문 표 전체 너비 기준

function asFloat(v) {
  if (v === undefined || v === null) return null;
  let s = String(v).replace(/,/g, "").replace(/\+/g, "").replace(/bp/gi, "").replace(/%/g, "");
  s = s.replace(/−/g, "-"); // 유니코드 마이너스 정규화
  const n = parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

function trend(v) {
  const n = asFloat(v);
  if (n === null) return { color: INK, symbol: "" };
  if (n > 0) return { color: UP, symbol: "▲" };
  if (n < 0) return { color: DOWN, symbol: "▼" };
  return { color: INK_SOFT, symbol: "-" };
}

function heatClass(pct) {
  const v = asFloat(pct);
  if (v === null) return "heat-flat";
  if (v >= 3) return "heat-up-3";
  if (v >= 1.5) return "heat-up-2";
  if (v > 0) return "heat-up-1";
  if (v === 0) return "heat-flat";
  if (v > -1.5) return "heat-down-1";
  if (v > -3) return "heat-down-2";
  return "heat-down-3";
}

function persistenceColor(text) {
  if (text === "높음") return INK;
  if (text === "중립") return INK_FAINT;
  return DOWN; // "약세 지속" 등
}

// ---- 텍스트/셀 헬퍼 ----

function run(text, opts = {}) {
  return new TextRun({ text: String(text ?? ""), font: FONT, ...opts });
}

function p(children, opts = {}) {
  const kids = Array.isArray(children) ? children : [run(children)];
  return new Paragraph({ children: kids, ...opts });
}

function noBorder() {
  const none = { style: BorderStyle.NONE, size: 0, color: WHITE };
  return { top: none, bottom: none, left: none, right: none };
}

function lineBorder(color = HY_TINT_LINE, size = 4) {
  const b = { style: BorderStyle.SINGLE, size, color };
  return { top: b, bottom: b, left: b, right: b };
}

function cell({ children, fill, width, colSpan, rowSpan, borders, valign, margins }) {
  return new TableCell({
    children: Array.isArray(children) ? children : [children],
    shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
    width: width ? { size: width, type: WidthType.DXA } : undefined,
    columnSpan: colSpan,
    rowSpan: rowSpan,
    borders: borders || lineBorder(),
    verticalAlign: valign || VerticalAlign.CENTER,
    margins: margins || { top: 60, bottom: 60, left: 100, right: 100 },
  });
}

function fullWidthTable(rows, colWidths) {
  return new Table({
    width: { size: PAGE_W, type: WidthType.DXA },
    columnWidths: colWidths,
    rows,
  });
}

// ---- 섹션 빌더 ----

function buildMasthead(logoPath, branchName) {
  const img = fs.existsSync(logoPath)
    ? new ImageRun({ data: fs.readFileSync(logoPath), transformation: { width: 90, height: 20 }, type: "png" })
    : run("한양증권", { bold: true });
  return fullWidthTable(
    [
      new TableRow({
        children: [
          cell({ children: p([img]), width: PAGE_W * 0.5, borders: noBorder() }),
          cell({
            children: p([run(`DAILY MARKET WRAP · ${branchName}`, { size: 16, bold: true, color: INK_SOFT })], { alignment: AlignmentType.RIGHT }),
            width: PAGE_W * 0.5,
            borders: noBorder(),
          }),
        ],
      }),
    ],
    [Math.round(PAGE_W * 0.5), Math.round(PAGE_W * 0.5)]
  );
}

function buildEyebrow(text) {
  return p([run(`  ${text}  `, { bold: true, size: 16, color: WHITE, shading: { type: ShadingType.CLEAR, fill: HY_DEEP, color: "auto" } })], { spacing: { after: 120 } });
}

function buildTitleRow(data) {
  const titleCell = [
    p([run(data.title, { bold: true, size: 30, color: INK })], { spacing: { after: 60 } }),
    p([run(data.subtitle, { size: 20, color: INK_SOFT })]),
  ];
  const bylineLines = [
    p([run(`${data.branch_name} ${data.department}`, { bold: true, size: 17, color: HY_DEEP })]),
    p([run(data.author, { bold: true, size: 16, color: INK })]),
    p([run(data.contact, { size: 16, color: INK_SOFT })]),
  ];
  return fullWidthTable(
    [
      new TableRow({
        children: [
          cell({ children: titleCell, width: PAGE_W * 0.68, borders: noBorder(), valign: VerticalAlign.TOP }),
          cell({ children: bylineLines, width: PAGE_W * 0.32, borders: lineBorder(HY_TINT_LINE, 6), valign: VerticalAlign.TOP }),
        ],
      }),
    ],
    [Math.round(PAGE_W * 0.68), Math.round(PAGE_W * 0.32)]
  );
}

function sectionHeading(text, note) {
  const kids = [run(text, { bold: true, size: 22, color: INK })];
  if (note) kids.push(run(`   ${note}`, { size: 15, color: INK_FAINT }));
  return p(kids, { spacing: { before: 260, after: 120 } });
}

function headerRow(labels, widths) {
  return new TableRow({
    children: labels.map((l, i) =>
      cell({
        children: p([run(l, { bold: true, size: 16, color: WHITE })], { alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.RIGHT }),
        fill: HY_DEEP,
        width: widths[i],
        borders: lineBorder(HY_DEEP, 4),
      })
    ),
  });
}

function buildIndicatorsTable(indicators) {
  const widths = [0.14, 0.16, 0.13, 0.13, 0.44].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["구분", "종가", "전일비", "등락률", "해석"], widths)];
  indicators.forEach((i) => {
    const t = trend(i.change_pt !== "" && i.change_pt !== undefined ? i.change_pt : i.change_pct);
    rows.push(
      new TableRow({
        children: [
          cell({ children: p([run(i.label, { bold: true, size: 17 })]), width: widths[0] }),
          cell({ children: p([run(i.close, { size: 17 })], { alignment: AlignmentType.RIGHT }), width: widths[1] }),
          cell({ children: p([run(i.change_pt, { size: 17, color: t.color, bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[2] }),
          cell({ children: p([run(i.change_pct, { size: 17, color: t.color, bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[3] }),
          cell({ children: p([run(i.note, { size: 15, color: INK_SOFT })]), width: widths[4] }),
        ],
      })
    );
  });
  return fullWidthTable(rows, widths);
}

function sectorCell(sector, colSpan, rowSpan) {
  const heat = HEAT[heatClass(sector.change_pct)];
  const children = [
    p([run(sector.name, { bold: true, size: 16, color: heat.fg })], { alignment: AlignmentType.CENTER }),
    p([run(`${sector.change_pct}%`, { bold: true, size: 17, color: heat.fg })], { alignment: AlignmentType.CENTER }),
  ];
  if (sector.top_stock) {
    children.push(p([run(sector.top_stock, { size: 11, color: heat.fg })], { alignment: AlignmentType.CENTER }));
  }
  return cell({
    children,
    fill: heat.fill,
    colSpan,
    rowSpan,
    borders: lineBorder(WHITE, 8),
    valign: VerticalAlign.CENTER,
  });
}

function buildSectorMap(sectorsIn) {
  const sectors = [...sectorsIn].sort((a, b) => (asFloat(b.weight) || 0) - (asFloat(a.weight) || 0));
  const colWidths = Array.from({ length: GRID_W }, () => Math.round(PAGE_W / GRID_W));
  const rows = [];

  if (sectors.length >= 9) {
    const [big, a1, a2, b1, b2, ...rest] = sectors;
    rows.push(new TableRow({ cantSplit: true, children: [sectorCell(big, 5, 2), sectorCell(a1, 4, 1), sectorCell(a2, 3, 1)] }));
    rows.push(new TableRow({ cantSplit: true, children: [sectorCell(b1, 4, 1), sectorCell(b2, 3, 1)] }));

    const row3 = rest.splice(0, 4);
    if (row3.length) {
      rows.push(new TableRow({ cantSplit: true, children: row3.map((s) => sectorCell(s, Math.floor(12 / row3.length), 1)) }));
    }
    while (rest.length) {
      const chunk = rest.splice(0, 6);
      const span = Math.floor(12 / chunk.length);
      const lastSpan = 12 - span * (chunk.length - 1);
      rows.push(
        new TableRow({
          cantSplit: true,
          children: chunk.map((s, i) => sectorCell(s, i === chunk.length - 1 ? lastSpan : span, 1)),
        })
      );
    }
  } else {
    // 섹터 수가 적을 때: 균등 그리드로 대체
    const perRow = Math.min(4, sectors.length) || 1;
    const span = Math.floor(GRID_W / perRow);
    for (let i = 0; i < sectors.length; i += perRow) {
      const chunk = sectors.slice(i, i + perRow);
      rows.push(new TableRow({ cantSplit: true, children: chunk.map((s) => sectorCell(s, span, 1)) }));
    }
  }

  return new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: colWidths, rows });
}

function buildIssueTable(stocks) {
  const widths = [0.13, 0.09, 0.41, 0.09, 0.28].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["종목", "등락률", "움직인 이유", "지속성", "언제·무엇을 확인"], widths)];
  stocks.forEach((s) => {
    const t = trend(s.change_pct);
    rows.push(
      new TableRow({
        cantSplit: true,
        children: [
          cell({ children: p([run(s.name, { size: 16, bold: true })]), width: widths[0] }),
          cell({ children: p([run(`${t.symbol} ${s.change_pct}%`, { size: 16, color: t.color, bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[1] }),
          cell({ children: p([run(s.reason, { size: 14, color: INK_SOFT })]), width: widths[2] }),
          cell({ children: p([run(s.persistence, { size: 15, color: persistenceColor(s.persistence), bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[3] }),
          cell({ children: p([run(s.checkpoint, { size: 14, color: INK_SOFT })]), width: widths[4] }),
        ],
      })
    );
  });
  return fullWidthTable(rows, widths);
}

function buildCalendarGrid(calendar) {
  const days = (calendar && calendar.days) || [];
  if (!days.length) return p([run("")]);
  const n = days.length;
  const colW = Math.round(PAGE_W / n);
  const widths = Array.from({ length: n }, () => colW);

  const head = new TableRow({
    cantSplit: true,
    children: days.map((d) =>
      cell({
        children: p(
          [run(d.date, { bold: true, size: 16, color: WHITE }), run(`  ${d.dow || ""}`, { size: 12, color: WHITE })],
          { alignment: AlignmentType.CENTER }
        ),
        fill: HY_DEEP,
        width: colW,
        borders: lineBorder(HY_DEEP, 4),
      })
    ),
  });

  const body = new TableRow({
    cantSplit: true,
    children: days.map((d) => {
      const paras = [];
      (d.events || []).forEach((e) => {
        const starsTxt = e.stars ? ` ${e.stars}` : "";
        paras.push(
          p(
            [run(`${e.time || ""}${starsTxt} `, { bold: true, size: 13, color: HY_MID }), run(e.title || "", { bold: true, size: 13, color: INK })],
            { spacing: { after: 20 } }
          )
        );
        if (e.note) paras.push(p([run(e.note, { size: 11, color: INK_SOFT })], { spacing: { after: 80 } }));
      });
      if (d.footer) paras.push(p([run(d.footer, { bold: true, size: 11, color: HY_DEEP })], { spacing: { before: 40 } }));
      if (!paras.length) paras.push(p([run("")]));
      return cell({ children: paras, width: colW, valign: VerticalAlign.TOP });
    }),
  });

  return fullWidthTable([head, body], widths);
}

function buildNextWeek(text) {
  if (!text) return null;
  return new Table({
    width: { size: PAGE_W, type: WidthType.DXA },
    columnWidths: [PAGE_W],
    rows: [
      new TableRow({
        children: [
          cell({
            children: p([run("다음 주 예고  ", { bold: true, size: 14, color: INK }), run(text, { size: 14, color: INK_SOFT })]),
            fill: HY_TINT,
            width: PAGE_W,
            borders: lineBorder(),
          }),
        ],
      }),
    ],
  });
}

function buildCompliance() {
  const text =
    "본 자료는 당사 지점 고객 및 임직원의 참고용으로 작성된 것으로 투자권유 또는 투자자문 목적이 아니며, 기재된 수치·전망은 오차가 발생할 수 있습니다. " +
    "투자의 최종 판단과 책임은 투자자 본인에게 있습니다. 당사 허락 없이 복사·대여·배포될 수 없습니다.";
  return [p([run(text, { size: 13, color: INK_FAINT })], { spacing: { before: 260 } })];
}

function buildFooter(data) {
  return p([run(`DAILY MARKET WRAP · ${data.branch_name}`, { size: 12, color: INK_FAINT })], {
    alignment: AlignmentType.CENTER,
    spacing: { before: 160 },
  });
}

function dateShort(dateStr) {
  if (!dateStr) return "";
  const [, m, d] = dateStr.split("-");
  return `${parseInt(m, 10)}/${parseInt(d, 10)}`;
}

// ---- 메인 ----

function main() {
  const [, , dataPath, outPath] = process.argv;
  if (!dataPath || !outPath) {
    console.error("사용법: node render_docx.js <data.json> <output.docx>");
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(dataPath, "utf-8"));
  const ds = dateShort(data.date);

  // render_report.py 와 동일한 파생값 계산 (weight_pct)
  const totalWeight = (data.sectors || []).reduce((sum, s) => sum + (asFloat(s.weight) || 0), 0) || 1;
  const sectors = (data.sectors || []).map((s) => ({ ...s, weight_pct: s.weight_pct ?? Math.round(((asFloat(s.weight) || 0) / totalWeight) * 1000) / 10 }));

  const logoPath = path.join(__dirname, "..", "..", "templates", "assets", "hy_logo_compact_color.png");
  const nextWeek = buildNextWeek((data.calendar || {}).next_week);

  const children = [
    buildMasthead(logoPath, data.branch_name),
    p([run("")]),
    buildEyebrow(data.eyebrow || "시장 마감 브리프"),
    buildTitleRow(data),

    sectionHeading("Ⅰ. 지수 · 시장 지표", `국내 지수·환율은 ${ds} 종가(한국거래소) · 금·유가는 ${ds} 장중 시세`),
    buildIndicatorsTable(data.indicators || []),

    sectionHeading("Ⅱ. 업종 동향 맵", `박스 크기 = 업종 시가총액 비중, 색·수치 = 해당 업종 대표종목 등락률 (${ds} 종가 기준)`),
    buildSectorMap(sectors),
    p([run(`자료: KRX, 언론 보도 종합 / 한양증권 ${data.branch_name} 재구성`, { size: 12, color: INK_FAINT })], { alignment: AlignmentType.RIGHT, spacing: { before: 60 } }),

    sectionHeading("Ⅲ. 이슈 종목 — 왜 움직였고, 이어질 것인가"),
    buildIssueTable(data.issue_stocks || []),

    sectionHeading("Ⅳ. 이번 주 캘린더", "시각은 한국시간(KST) · ★★★ = 지수 방향을 바꿀 수 있는 이벤트"),
    buildCalendarGrid(data.calendar),
    ...(nextWeek ? [p([run("")]), nextWeek] : []),

    ...buildCompliance(),
    buildFooter(data),
  ];

  const doc = new Document({
    styles: { default: { document: { run: { font: FONT, size: 18 } } } },
    sections: [
      {
        properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 720, bottom: 720, left: 720, right: 720 } } },
        children,
      },
    ],
  });

  Packer.toBuffer(doc).then((buf) => {
    fs.writeFileSync(outPath, buf);
    console.log(`생성 완료: ${outPath}`);
  });
}

main();
