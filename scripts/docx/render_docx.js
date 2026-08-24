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

function stars(n) {
  const k = Number(n) || 2;
  return "★".repeat(k) + "☆".repeat(3 - k);
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
    p([run(`${data.date} (${data.weekday}) 장마감`, { bold: true, size: 18, color: INK })]),
    p([run(`발행 ${data.generated_at} · 당일 배포`, { size: 16, color: INK_SOFT })], { spacing: { after: 100 } }),
    p([run(`${data.branch_name} ${data.department}`, { bold: true, size: 17, color: HY_DEEP })]),
    p([run(data.author, { size: 16, color: INK_SOFT })]),
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

function buildSkkBox(data) {
  const rows = [
    ["SIGNAL", data.signal],
    ["KEY", data.key_point],
    ["STEP", data.step],
  ];
  return fullWidthTable(
    rows.map(
      ([label, text]) =>
        new TableRow({
          children: [
            cell({
              children: p([run(label, { bold: true, size: 15, color: WHITE })], { alignment: AlignmentType.CENTER }),
              fill: HY_DEEP,
              width: PAGE_W * 0.1,
              borders: lineBorder(HY_TINT_LINE, 4),
            }),
            cell({ children: p([run(text, { size: 18 })]), width: PAGE_W * 0.9, borders: lineBorder(HY_TINT_LINE, 4) }),
          ],
        })
    ),
    [Math.round(PAGE_W * 0.1), Math.round(PAGE_W * 0.9)]
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

function infoBox(title, lines, width) {
  return new Table({
    width: { size: width, type: WidthType.DXA },
    columnWidths: [width],
    rows: [
      new TableRow({ children: [cell({ children: p([run(title, { bold: true, size: 16, color: HY_DEEP })]), fill: HY_TINT, width, borders: lineBorder() })] }),
      new TableRow({ children: [cell({ children: lines.map((l) => p([run(l, { size: 15 })], { spacing: { after: 40 } })), width, borders: lineBorder() })] }),
    ],
  });
}

function pngDimensions(buf) {
  // PNG 헤더의 IHDR 청크에서 폭/높이를 읽는다 (오프셋 16, 24: 각 4바이트 빅엔디언).
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function buildChartImage(chartPath) {
  if (!chartPath || !fs.existsSync(chartPath)) return null;
  const buf = fs.readFileSync(chartPath);
  const { width, height } = pngDimensions(buf);
  const targetWidthPx = Math.round((PAGE_W / 1440) * 96); // dxa -> 96dpi 픽셀, 본문 전체 폭
  const targetHeightPx = Math.round((height / width) * targetWidthPx);
  return p([new ImageRun({ data: buf, transformation: { width: targetWidthPx, height: targetHeightPx }, type: "png" })], {
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
  });
}

function buildFlowsBreadth(flows, breadth) {
  const half = Math.round(PAGE_W * 0.49);
  const flowLines = [
    `KOSPI 외국인 ${flows.kospi.foreign} · 기관 ${flows.kospi.inst} · 개인 ${flows.kospi.retail}`,
    `KOSDAQ 외국인 ${flows.kosdaq.foreign} · 기관 ${flows.kosdaq.inst} · 개인 ${flows.kosdaq.retail}`,
    `선물 ${flows.futures}`,
  ];
  const breadthLines = [
    `상승/하락 ${breadth.advance_decline} — ${breadth.note}`,
    `거래대금 ${breadth.trading_value}`,
    `신용잔고 ${breadth.margin_balance}`,
  ];
  return new Table({
    width: { size: PAGE_W, type: WidthType.DXA },
    columnWidths: [half, half],
    rows: [
      new TableRow({
        children: [
          cell({ children: [infoBox("투자자별 순매수 (억원)", flowLines, half)], width: half, borders: noBorder(), margins: { top: 0, bottom: 0, left: 0, right: 80 } }),
          cell({ children: [infoBox("시장 폭 (Breadth)", breadthLines, half)], width: half, borders: noBorder(), margins: { top: 0, bottom: 0, left: 80, right: 0 } }),
        ],
      }),
    ],
  });
}

function sectorCell(sector, colSpan, rowSpan) {
  const heat = HEAT[heatClass(sector.change_pct)];
  return cell({
    children: [
      p([run(sector.name, { bold: true, size: 16, color: heat.fg })], { alignment: AlignmentType.CENTER }),
      p([run(`${sector.change_pct}%`, { bold: true, size: 17, color: heat.fg })], { alignment: AlignmentType.CENTER }),
      p([run(`${sector.weight_pct ?? sector.weight}%`, { size: 12, color: heat.fg })], { alignment: AlignmentType.CENTER }),
    ],
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
    rows.push(new TableRow({ children: [sectorCell(big, 5, 2), sectorCell(a1, 4, 1), sectorCell(a2, 3, 1)] }));
    rows.push(new TableRow({ children: [sectorCell(b1, 4, 1), sectorCell(b2, 3, 1)] }));

    const row3 = rest.splice(0, 4);
    if (row3.length) {
      rows.push(new TableRow({ children: row3.map((s) => sectorCell(s, Math.floor(12 / row3.length), 1)) }));
    }
    while (rest.length) {
      const chunk = rest.splice(0, 6);
      const span = Math.floor(12 / chunk.length);
      const lastSpan = 12 - span * (chunk.length - 1);
      rows.push(
        new TableRow({
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
      rows.push(new TableRow({ children: chunk.map((s) => sectorCell(s, span, 1)) }));
    }
  }

  return new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: colWidths, rows });
}

function buildIssueTable(stocks) {
  const widths = [0.14, 0.09, 0.4, 0.09, 0.28].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["종목", "등락률", "움직인 이유", "지속성", "언제·무엇을 확인"], widths)];
  stocks.forEach((s) => {
    const t = trend(s.change_pct);
    rows.push(
      new TableRow({
        children: [
          cell({ children: p([run(`${s.name}(${s.ticker})`, { size: 16, bold: true })]) , width: widths[0] }),
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

function buildCalendarTable(items) {
  const widths = [0.14, 0.28, 0.1, 0.48].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["일시", "이벤트", "중요도", "체크포인트 / 영향 종목"], widths)];
  items.forEach((c) => {
    const high = Number(c.importance) >= 3;
    rows.push(
      new TableRow({
        children: [
          cell({ children: p([run(c.datetime, { size: 15, bold: true })]), width: widths[0], fill: high ? HY_TINT : undefined }),
          cell({ children: p([run(c.event, { size: 15, bold: high, color: high ? INK : undefined })]), width: widths[1], fill: high ? HY_TINT : undefined }),
          cell({ children: p([run(stars(c.importance), { size: 15, color: HY_MID })], { alignment: AlignmentType.RIGHT }), width: widths[2], fill: high ? HY_TINT : undefined }),
          cell({ children: p([run(c.checkpoint, { size: 14, color: INK_SOFT })]), width: widths[3], fill: high ? HY_TINT : undefined }),
        ],
      })
    );
  });
  return fullWidthTable(rows, widths);
}

function buildStanceTable(stance) {
  const third = Math.round(PAGE_W / 3);
  const cols = [
    ["유지", stance.maintain],
    ["축소", stance.reduce],
    ["현금·안내", stance.cash],
  ];
  return new Table({
    width: { size: PAGE_W, type: WidthType.DXA },
    columnWidths: [third, third, third],
    rows: [
      new TableRow({
        children: cols.map(([label]) =>
          cell({ children: p([run(label, { bold: true, size: 16, color: WHITE })], { alignment: AlignmentType.CENTER }), fill: HY_DEEP, width: third })
        ),
      }),
      new TableRow({
        children: cols.map(([, text]) => cell({ children: p([run(text, { size: 15 })]), width: third, valign: VerticalAlign.TOP })),
      }),
    ],
  });
}

function buildCompliance(branchName) {
  const bullets = [
    "본 자료는 지점 내부 참고자료로, 제3자에게 사전 제공된 사실이 없습니다.",
    "작성자는 자료 작성일 현재 본 자료에 언급된 종목과 재산적 이해관계가 없습니다.",
    "본 자료의 수치는 언론 보도 및 시장 데이터를 정리한 것으로 당사 리서치센터의 공식 견해가 아니며, 정확성·완전성을 보장하지 않습니다.",
  ];
  return [
    p([run("Compliance Notice", { bold: true, size: 16, color: INK })], { spacing: { before: 260, after: 60 } }),
    ...bullets.map((b) => p([run(`·  ${b}`, { size: 13, color: INK_FAINT })], { spacing: { after: 20 } })),
  ];
}

function buildFooter(data) {
  return p(
    [
      run(
        `작성·문의: 한양증권 ${data.branch_name} ${data.department} ${data.author} (${data.contact}) · 투자 권유 목적이 아니며 투자판단의 책임은 투자자 본인에게 있습니다.`,
        { size: 12, color: INK_FAINT }
      ),
    ],
    { spacing: { before: 160 } }
  );
}

// ---- 메인 ----

function main() {
  const [, , dataPath, outPath] = process.argv;
  if (!dataPath || !outPath) {
    console.error("사용법: node render_docx.js <data.json> <output.docx>");
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

  // render_report.py 와 동일한 파생값 계산 (weight_pct)
  const totalWeight = (data.sectors || []).reduce((sum, s) => sum + (asFloat(s.weight) || 0), 0) || 1;
  const sectors = (data.sectors || []).map((s) => ({ ...s, weight_pct: s.weight_pct ?? Math.round(((asFloat(s.weight) || 0) / totalWeight) * 1000) / 10 }));

  const logoPath = path.join(__dirname, "..", "..", "templates", "assets", "hy_logo_compact_color.png");

  const children = [
    buildMasthead(logoPath, data.branch_name),
    p([run("")]),
    buildEyebrow(data.eyebrow || "시장 마감 브리프"),
    buildTitleRow(data),
    p([run("")]),
    buildSkkBox(data),

    sectionHeading("Ⅰ. 지수 · 대외 지표"),
    buildIndicatorsTable(data.indicators || []),
    p([run("")]),
    buildFlowsBreadth(data.flows || {}, data.breadth || {}),
    buildChartImage(data.chart_png_path) || p([run("")]),

    sectionHeading("Ⅱ. 업종 동향 맵", "박스 크기 = 시가총액 비중, 색 = 당일 등락률"),
    buildSectorMap(sectors),
    p([run(`자료: KRX, 한양증권 ${data.branch_name} 재구성`, { size: 12, color: INK_FAINT })], { alignment: AlignmentType.RIGHT, spacing: { before: 60 } }),
    p([run(data.sector_prose || "", { size: 15 })], { spacing: { before: 100 } }),

    sectionHeading("Ⅲ. 이슈 종목 — 왜 움직였고, 이어질 것인가"),
    buildIssueTable(data.issue_stocks || []),

    sectionHeading("Ⅳ. 캘린더 — 언제, 무엇을, 왜 봐야 하나", "시각은 한국시간 기준"),
    buildCalendarTable(data.calendar || []),

    sectionHeading("지점 대응 요약 — 이번 주"),
    buildStanceTable(data.stance || {}),

    ...buildCompliance(data.branch_name),
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
