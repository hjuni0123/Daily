#!/usr/bin/env node
/**
 * 데일리 마켓 브리핑 -> .docx 렌더러.
 *
 * scripts/render_report.py 와 동일한 데이터 JSON(스키마는 docs/AUTOMATION_GUIDE.md 참고)을
 * 읽어 "Daily Market Close" 워드 양식으로 렌더링한다.
 *
 * 사용법:
 *   cd scripts/docx && npm install   (최초 1회)
 *   node render_docx.js ../../data/2026-08-26.json ../../reports/2026-08-26_market_report.docx
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

const WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"];

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

function bucketHeatClass(bucket) {
  const b = String(bucket || "").trim();
  if (b.includes("상한가") || b.includes("급등")) return "heat-up-3";
  if (b.includes("하한가") || b.includes("급락")) return "heat-down-3";
  let m = b.match(/\+([0-9.]+)/);
  if (m) return parseFloat(m[1]) >= 2 ? "heat-up-2" : "heat-up-1";
  m = b.match(/[−-]([0-9.]+)/);
  if (m) return parseFloat(m[1]) >= 2 ? "heat-down-2" : "heat-down-1";
  if (b.includes("강보합")) return "heat-up-1";
  if (b.includes("약보합")) return "heat-down-1";
  return "heat-flat";
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

function buildTitleRow(data, dateFull) {
  const titleCell = [
    p([run(`${dateFull} 장 마감 기준`, { size: 15, color: INK_FAINT })], { spacing: { after: 40 } }),
    p([run(data.title, { bold: true, size: 28, color: INK })], { spacing: { after: 60 } }),
    p([run(data.lead || "", { size: 17, color: INK_SOFT })]),
  ];
  const bylineLines = [
    p(
      [
        run(`${data.branch_name} ${data.department} ${data.author}`, { bold: true, size: 15, color: HY_DEEP }),
        run(` · ${data.contact}`, { size: 14, color: INK_SOFT }),
      ],
      { alignment: AlignmentType.RIGHT }
    ),
    p([run("DAILY MARKET WRAP", { size: 13, bold: true, color: HY_MID })], { alignment: AlignmentType.RIGHT, spacing: { before: 20 } }),
  ];
  return fullWidthTable(
    [
      new TableRow({
        children: [
          cell({ children: titleCell, width: PAGE_W * 0.68, borders: noBorder(), valign: VerticalAlign.TOP }),
          cell({ children: bylineLines, width: PAGE_W * 0.32, borders: noBorder(), valign: VerticalAlign.TOP }),
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
  const widths = [0.16, 0.13, 0.13, 0.14, 0.44].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["구분", "시가", "장중 고점", "종가", "비고"], widths)];
  indicators.forEach((i) => {
    const t = trend(i.close);
    rows.push(
      new TableRow({
        cantSplit: true,
        children: [
          cell({ children: p([run(i.label, { bold: true, size: 17 })]), width: widths[0] }),
          cell({ children: p([run(i.open, { size: 16 })], { alignment: AlignmentType.RIGHT }), width: widths[1] }),
          cell({ children: p([run(i.day_high, { size: 16 })], { alignment: AlignmentType.RIGHT }), width: widths[2] }),
          cell({ children: p([run(i.close, { size: 17, color: t.color, bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[3] }),
          cell({ children: p([run(i.note, { size: 14, color: INK_SOFT })]), width: widths[4] }),
        ],
      })
    );
  });
  return fullWidthTable(rows, widths);
}

function sectorCell(sector, colSpan, rowSpan) {
  const heat = HEAT[bucketHeatClass(sector.bucket)];
  const children = [
    p([run(sector.name, { bold: true, size: 16, color: heat.fg })], { alignment: AlignmentType.CENTER }),
    p([run(sector.bucket, { bold: true, size: 17, color: heat.fg })], { alignment: AlignmentType.CENTER }),
  ];
  if (sector.detail) {
    children.push(p([run(sector.detail, { size: 11, color: heat.fg })], { alignment: AlignmentType.CENTER }));
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

function buildCheckpointsTable(checkpoints) {
  const widths = [0.13, 0.16, 0.16, 0.55].map((f) => Math.round(PAGE_W * f));
  const rows = [headerRow(["섹터", "관심 종목", "오늘의 관점", "근거"], widths)];
  checkpoints.forEach((c) => {
    rows.push(
      new TableRow({
        cantSplit: true,
        children: [
          cell({ children: p([run(c.sector, { size: 16, bold: true })]), width: widths[0] }),
          cell({ children: p([run(c.stocks, { size: 14 })], { alignment: AlignmentType.RIGHT }), width: widths[1] }),
          cell({ children: p([run(c.view, { size: 14, color: HY_DEEP, bold: true })], { alignment: AlignmentType.RIGHT }), width: widths[2] }),
          cell({ children: p([run(c.rationale, { size: 14, color: INK_SOFT })]), width: widths[3] }),
        ],
      })
    );
  });
  return fullWidthTable(rows, widths);
}

function buildCalendarGrid(calendar) {
  const cols = calendar || [];
  if (!cols.length) return p([run("")]);
  const n = cols.length;
  const colW = Math.round(PAGE_W / n);
  const widths = Array.from({ length: n }, () => colW);

  const head = new TableRow({
    cantSplit: true,
    children: cols.map((c) =>
      cell({
        children: p(
          [run(c.date, { bold: true, size: 16, color: WHITE }), run(`  ${c.dow || ""}`, { size: 12, color: WHITE })],
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
    children: cols.map((c) => {
      const paras = [p([run(c.headline || "", { bold: true, size: 13, color: INK })], { spacing: { after: 40 } })];
      (c.detail || "").split("\n").forEach((line) => {
        if (line.trim()) paras.push(p([run(line, { size: 11, color: INK_SOFT })], { spacing: { after: 20 } }));
      });
      return cell({ children: paras, width: colW, valign: VerticalAlign.TOP });
    }),
  });

  const footRow = new TableRow({
    cantSplit: true,
    children: cols.map((c) =>
      cell({
        children: p([run(c.footer || "", { bold: true, size: 11, color: HY_DEEP })], { alignment: AlignmentType.CENTER }),
        fill: HY_TINT,
        width: colW,
        borders: lineBorder(),
      })
    ),
  });

  return fullWidthTable([head, body, footRow], widths);
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

function dateFull(dateStr) {
  if (!dateStr) return "";
  const [y, m, d] = dateStr.split("-").map((v) => parseInt(v, 10));
  const jsDay = new Date(y, m - 1, d).getDay(); // 0=Sun..6=Sat
  const dow = WEEKDAY_KO[(jsDay + 6) % 7];
  return `${y}년 ${m}월 ${d}일(${dow})`;
}

// ---- 메인 ----

function main() {
  const [, , dataPath, outPath] = process.argv;
  if (!dataPath || !outPath) {
    console.error("사용법: node render_docx.js <data.json> <output.docx>");
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(dataPath, "utf-8"));
  const df = dateFull(data.date);

  const logoPath = path.join(__dirname, "..", "..", "templates", "assets", "hy_logo_compact_color.png");

  const children = [
    buildMasthead(logoPath, data.branch_name),
    p([run("")]),
    buildTitleRow(data, df),

    sectionHeading("1. 지수 및 시장 지표"),
    buildIndicatorsTable(data.indicators || []),
    p([run(`${data.flows_note || ""} `, { size: 13, color: INK_SOFT }), run(data.flows_source || "", { size: 12, color: INK_FAINT })], { spacing: { before: 60 } }),

    sectionHeading("2. 업종 동향", "박스 크기 = 업종 시가총액 비중(근사), 색·표시 = 방향성"),
    buildSectorMap(data.sectors || []),
    p([run("자료: 한국거래소 업종지수, 언론 보도 종합", { size: 12, color: INK_FAINT })], { alignment: AlignmentType.RIGHT, spacing: { before: 60 } }),
    p([run(data.sector_analysis || "", { size: 14, color: INK_SOFT })], { spacing: { before: 100 } }),

    sectionHeading("3. 이번 주 일정", "시각은 한국시간(KST) 기준"),
    buildCalendarGrid(data.calendar),

    sectionHeading("4. 금일 체크포인트", "작성자 개인 견해이며 투자권유가 아닙니다"),
    buildCheckpointsTable(data.checkpoints || []),

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
