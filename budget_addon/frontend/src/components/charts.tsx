/**
 * Grafikler: gelir/harcama sütunları, net varlık çizgisi, günlük harcama ısı
 * haritası ve gelirden harcama gruplarına para akışı.
 *
 * Kütüphane kullanılmaz; çizim CSS ve küçük SVG'lerle yapılır. Tutarlar
 * sunucudan biçimlenmiş gelir; kuruş değeri yalnızca boyut için kullanılır.
 * Her grafiğin üzerine gelince (veya dokununca) değeri gösteren bir satırı
 * vardır; renk tek başına anlam taşımaz, gösterge ve metin her zaman yanındadır.
 */

import { useMemo, useState } from "react";

import type { DailySpending, FlowMonth, MoneyFlow, NetWorthPoint } from "../api";
import { formatMinor, longDate, monthName, shortMonthName } from "../format";
import { Empty } from "./ui";

// ---------------------------------------------------------------------------
// Gelir ve harcama
// ---------------------------------------------------------------------------

export function FlowBars({ months }: { months: FlowMonth[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const peak = Math.max(1, ...months.flatMap((m) => [m.income.minor, m.spending.minor]));
  if (!months.some((m) => m.income.minor > 0 || m.spending.minor > 0)) {
    return <Empty icon="chart" title="Bu dönemde gelir veya harcama kaydı yok" />;
  }
  const focus = months[hovered ?? months.length - 1];
  return (
    <>
      <div
        className="chart flow"
        style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }}
        onMouseLeave={() => setHovered(null)}
      >
        {months.map((month, index) => (
          <div
            key={`${month.year}-${month.month}`}
            className={hovered === index ? "chart-col is-hovered" : "chart-col"}
            onMouseEnter={() => setHovered(index)}
            onClick={() => setHovered(index)}
            aria-label={`${monthName(month.year, month.month)}: gelir ${month.income.formatted}, harcama ${month.spending.formatted}`}
          >
            <div className="chart-bars">
              <div
                className="chart-bar income"
                style={{ height: `${(Math.max(month.income.minor, 0) * 100) / peak}%` }}
              />
              <div
                className="chart-bar spend"
                style={{ height: `${(Math.max(month.spending.minor, 0) * 100) / peak}%` }}
              />
            </div>
            <span className="chart-label">{shortMonthName(month.month)}</span>
          </div>
        ))}
      </div>
      <div className="chart-tip" aria-live="polite">
        <strong>{monthName(focus.year, focus.month)}</strong>
        <div className="row wrap">
          <span className="tip-row">
            <i style={{ background: "var(--viz-income)" }} /> Gelir {focus.income.formatted}
          </span>
          <span className="tip-row">
            <i style={{ background: "var(--viz-spend)" }} /> Harcama {focus.spending.formatted}
          </span>
          <span className={focus.net.minor < 0 ? "danger-text" : "success-text"}>
            Fark {focus.net.formatted}
          </span>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Net varlik
// ---------------------------------------------------------------------------

const LINE_W = 600;
const LINE_H = 200;
const PAD = { top: 12, right: 12, bottom: 22, left: 12 };

function compact(minor: number): string {
  const major = Math.round(minor / 100);
  const abs = Math.abs(major);
  if (abs >= 1_000_000) return `${(major / 1_000_000).toFixed(1).replace(".", ",")} Mn`;
  if (abs >= 1_000) return `${Math.round(major / 1_000)} B`;
  return String(major);
}

export function NetWorthLine({ points }: { points: NetWorthPoint[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const values = points.map((point) => point.net.minor);
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  const innerW = LINE_W - PAD.left - PAD.right;
  const innerH = LINE_H - PAD.top - PAD.bottom;
  const x = (index: number) =>
    PAD.left + (points.length === 1 ? innerW / 2 : (index * innerW) / (points.length - 1));
  const y = (value: number) => PAD.top + ((max - value) * innerH) / (max - min || 1);

  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.net.minor)}`).join(" ");
  const area = `${path} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const focusIndex = hovered ?? points.length - 1;
  const focus = points[focusIndex];
  const step = points.length > 1 ? innerW / (points.length - 1) : innerW;

  if (!points.some((point) => point.assets.minor !== 0 || point.card_debt.minor !== 0)) {
    return (
      <Empty
        icon="chart"
        title="Henüz net varlık geçmişi yok"
        text="Hesaplarınızın bakiyesini girdikçe ay sonu net varlığınız burada çizilir."
      />
    );
  }

  return (
    <>
      <div className="line-wrap">
      <span className="line-max" aria-hidden="true">
        {compact(max)} TL
      </span>
      <span
        className="line-dot"
        aria-hidden="true"
        style={{
          left: `${(x(focusIndex) * 100) / LINE_W}%`,
          top: `${(y(focus.net.minor) * 100) / LINE_H}%`,
        }}
      />
      <svg
        className="line-chart"
        viewBox={`0 0 ${LINE_W} ${LINE_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Ay sonlarına göre net varlık"
        onMouseLeave={() => setHovered(null)}
      >
        <line className="grid-line" x1={PAD.left} x2={LINE_W - PAD.right} y1={y(max)} y2={y(max)} vectorEffect="non-scaling-stroke" />
        <line className="baseline" x1={PAD.left} x2={LINE_W - PAD.right} y1={y(0)} y2={y(0)} vectorEffect="non-scaling-stroke" />
        <path className="area" d={area} />
        <path className="series" d={path} vectorEffect="non-scaling-stroke" />
        {hovered !== null && (
          <line
            className="crosshair"
            x1={x(hovered)}
            x2={x(hovered)}
            y1={PAD.top}
            y2={LINE_H - PAD.bottom}
            vectorEffect="non-scaling-stroke"
          />
        )}
        {points.map((point, index) => (
          <rect
            key={point.when}
            className="hit"
            x={x(index) - step / 2}
            y={0}
            width={step}
            height={LINE_H}
            onMouseEnter={() => setHovered(index)}
            onClick={() => setHovered(index)}
          />
        ))}
      </svg>
      </div>
      <div className="line-axis" aria-hidden="true">
        <span>{shortMonthName(Number(points[0].when.slice(5, 7)))}</span>
        <span>{shortMonthName(Number(points[points.length - 1].when.slice(5, 7)))}</span>
      </div>
      <div className="chart-tip" aria-live="polite">
        <strong>{longDate(focus.when)}</strong>
        <div className="row wrap">
          <span className="tip-row">
            <i style={{ background: "var(--viz-net)" }} /> Net {focus.net.formatted}
          </span>
          <span className="muted">Varlık {focus.assets.formatted}</span>
          <span className="muted">Kart borcu {focus.card_debt.formatted}</span>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Gunluk harcama isi haritasi
// ---------------------------------------------------------------------------

const WEEKDAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const LEVELS = 5;

export function DailyHeatmap({ data }: { data: DailySpending }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const peak = Math.max(0, ...data.days.map((day) => day.minor));
  // Pazartesi ile baslayan hafta: getDay() pazari 0 verir.
  const offset = (new Date(data.year, data.month - 1, 1).getDay() + 6) % 7;
  const level = (minor: number) =>
    minor <= 0 || peak <= 0 ? 0 : Math.max(1, Math.ceil((minor * LEVELS) / peak));
  const focus = hovered !== null ? data.days[hovered] : null;

  return (
    <>
      <div className="heatmap" onMouseLeave={() => setHovered(null)}>
        {WEEKDAYS.map((name) => (
          <span className="weekday" key={name}>
            {name}
          </span>
        ))}
        {Array.from({ length: offset }, (_, index) => (
          <span className="heat-cell blank" key={`blank-${index}`} />
        ))}
        {data.days.map((day, index) => {
          const classes = ["heat-cell", `l${level(day.minor)}`];
          if (hovered === index) classes.push("is-hovered");
          return (
            <button
              type="button"
              key={index}
              className={classes.join(" ")}
              onMouseEnter={() => setHovered(index)}
              onFocus={() => setHovered(index)}
              onClick={() => setHovered(index)}
              aria-label={`${index + 1} ${monthName(data.year, data.month)}: ${day.formatted}`}
            >
              <span className="day">{index + 1}</span>
              {day.minor > 0 && <span className="amount">{compact(day.minor)}</span>}
            </button>
          );
        })}
      </div>
      <div className="heat-scale" aria-hidden="true">
        Az
        {Array.from({ length: LEVELS }, (_, index) => (
          <i key={index} style={{ background: `var(--viz-seq-${index + 1})` }} />
        ))}
        Çok
      </div>
      <div className="chart-tip" aria-live="polite">
        {focus !== null && hovered !== null ? (
          <>
            <strong>
              {hovered + 1} {monthName(data.year, data.month)}
            </strong>{" "}
            · {focus.formatted}
          </>
        ) : (
          <span className="muted">
            Ay toplamı {data.total.formatted}. Bir güne gelin veya dokunun.
          </span>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Para akisi
// ---------------------------------------------------------------------------

const FLOW_W = 640;
const NODE_W = 14;
const GAP = 8;
const MIN_NODE = 30;

interface Placed {
  name: string;
  minor: number;
  formatted: string;
  y: number;
  h: number;
  kind: "income" | "spend" | "rest";
  detail?: string;
}

function stack(
  items: { name: string; minor: number; formatted: string; kind: Placed["kind"]; detail?: string }[],
  scale: number,
): Placed[] {
  let cursor = 0;
  return items.map((item) => {
    const h = Math.max(MIN_NODE, item.minor * scale);
    const placed = { ...item, y: cursor, h };
    cursor += h + GAP;
    return placed;
  });
}

export function MoneyFlowDiagram({ flow }: { flow: MoneyFlow }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const layout = useMemo(() => {
    const rest = flow.remaining.minor;
    const left = flow.sources.map((source) => ({
      name: source.name,
      minor: source.amount.minor,
      formatted: source.amount.formatted,
      kind: "income" as const,
    }));
    if (rest < 0) {
      left.push({ name: "Açık (gelirden fazla)", minor: -rest, formatted: formatMinor(-rest), kind: "income" });
    }
    const right = flow.targets.map((target) => ({
      name: target.name,
      minor: target.amount.minor,
      formatted: target.amount.formatted,
      kind: "spend" as Placed["kind"],
      detail: target.categories.map((c) => `${c.name} ${c.amount.formatted}`).join(" · "),
    }));
    if (rest > 0) {
      right.push({ name: "Kalan", minor: rest, formatted: formatMinor(rest), kind: "rest", detail: "" });
    }
    const total = Math.max(
      1,
      left.reduce((sum, item) => sum + item.minor, 0),
      right.reduce((sum, item) => sum + item.minor, 0),
    );
    const scale = 220 / total;
    const placedLeft = stack(left, scale);
    const placedRight = stack(right, scale);
    const bottom = (nodes: Placed[]) =>
      nodes.length ? nodes[nodes.length - 1].y + nodes[nodes.length - 1].h : 0;
    const height = Math.max(bottom(placedLeft), bottom(placedRight), 120);
    return { left: placedLeft, right: placedRight, height, total };
  }, [flow]);

  if (flow.income.minor === 0 && flow.spending.minor === 0) {
    return <Empty icon="chart" title="Bu ay gelir veya harcama kaydı yok" />;
  }

  const leftX = 150;
  const rightX = FLOW_W - 170;
  // Iki tarafin toplami esittir (gelir + acik = harcama + kalan). Her
  // kaynaktan her gruba, ikisinin paylarinin carpimi kadar bant cizilir;
  // bant kalinligi dugum yuksekligiyle orantilidir.
  const links: { key: string; path: string; rest: boolean }[] = [];
  const leftUsed = layout.left.map(() => 0);
  const rightUsed = layout.right.map(() => 0);
  layout.right.forEach((target, ti) => {
    layout.left.forEach((source, si) => {
      const fraction = (source.minor * target.minor) / (layout.total * layout.total);
      const h1 = (fraction * layout.total * source.h) / Math.max(source.minor, 1);
      const h2 = (fraction * layout.total * target.h) / Math.max(target.minor, 1);
      if (h1 <= 0 || h2 <= 0) return;
      const y1 = source.y + leftUsed[si];
      const y2 = target.y + rightUsed[ti];
      leftUsed[si] += h1;
      rightUsed[ti] += h2;
      const x1 = leftX + NODE_W;
      const x2 = rightX;
      const mid = (x1 + x2) / 2;
      links.push({
        key: `${source.name}->${target.name}`,
        rest: target.kind === "rest",
        path: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2} L${x2},${y2 + h2} C${mid},${y2 + h2} ${mid},${y1 + h1} ${x1},${y1 + h1} Z`,
      });
    });
  });

  const focus = layout.right.find((node) => node.name === hovered);

  return (
    <>
      <svg
        className="flow-diagram"
        viewBox={`0 -6 ${FLOW_W} ${layout.height + 12}`}
        role="img"
        aria-label="Gelirin harcama gruplarına dağılımı"
        onMouseLeave={() => setHovered(null)}
      >
        {links.map((link) => (
          <path
            key={link.key}
            className={[
              "link",
              link.rest ? "rest" : "",
              hovered && link.key.endsWith(`->${hovered}`) ? "is-hovered" : "",
            ].join(" ")}
            d={link.path}
          />
        ))}
        {layout.left.map((node) => (
          <g key={`l-${node.name}`}>
            <rect className="node-income" x={leftX} y={node.y} width={NODE_W} height={node.h} rx={3} />
            <text x={leftX - 8} y={node.y + node.h / 2} textAnchor="end" dominantBaseline="middle">
              {node.name}
            </text>
            <text
              className="value"
              x={leftX - 8}
              y={node.y + node.h / 2 + 14}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {node.formatted}
            </text>
          </g>
        ))}
        {layout.right.map((node) => (
          <g
            key={`r-${node.name}`}
            onMouseEnter={() => setHovered(node.name)}
            onClick={() => setHovered(node.name)}
          >
            <rect
              className={node.kind === "rest" ? "node-rest" : "node-spend"}
              x={rightX}
              y={node.y}
              width={NODE_W}
              height={node.h}
              rx={3}
            />
            <text x={rightX + NODE_W + 8} y={node.y + node.h / 2} dominantBaseline="middle">
              {node.name}
            </text>
            <text
              className="value"
              x={rightX + NODE_W + 8}
              y={node.y + node.h / 2 + 14}
              dominantBaseline="middle"
            >
              {node.formatted}
            </text>
          </g>
        ))}
      </svg>
      <div className="chart-tip" aria-live="polite">
        {focus ? (
          <>
            <strong>{focus.name}</strong> · {focus.formatted}
            {focus.detail && <div className="muted small">{focus.detail}</div>}
          </>
        ) : (
          <span className="muted">
            Gelir {flow.income.formatted} · Harcama {flow.spending.formatted} ·{" "}
            {flow.remaining.minor >= 0 ? "Kalan" : "Açık"} {formatMinor(Math.abs(flow.remaining.minor))}
          </span>
        )}
      </div>
    </>
  );
}
