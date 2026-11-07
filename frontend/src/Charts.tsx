import { percentage } from "./api";
import { Panel, Table } from "./ui";
import type { Dataset, Ratio } from "./types";
const colors = ["var(--muted)", "var(--blue)", "var(--green)"];
export function latencyPoints(data: Dataset) {
  return Object.keys(data.summary.methods).map((name) => ({
    name,
    values: data.trials.flatMap((t) =>
      t.phases.flatMap((p) => {
        const value = p.methods[name]?.elapsed_seconds;
        return typeof value === "number" && Number.isFinite(value) && value > 0
          ? [value]
          : [];
      }),
    ),
  }));
}
export function intervalText(metric: Ratio) {
  return metric.wilson_95
    ? `${(metric.wilson_95[0] * 100).toFixed(1)}–${(metric.wilson_95[1] * 100).toFixed(1)}%`
    : "Undefined";
}
export default function ComparisonCharts({
  data,
  partial,
}: {
  data: Dataset;
  partial: boolean;
}) {
  const points = latencyPoints(data);
  const all = points.flatMap((p) => p.values);
  const min = all.length ? Math.floor(Math.log10(Math.min(...all))) : -2;
  const max = all.length
    ? Math.max(min + 1, Math.ceil(Math.log10(Math.max(...all))))
    : 1;
  const ticks = Array.from(
    { length: max - min + 1 },
    (_, i) => 10 ** (min + i),
  );
  const y = (v: number) => 210 - ((Math.log10(v) - min) / (max - min)) * 180;
  return (
    <div className="grid two charts-grid">
      <Panel
        title="Coverage and detection"
        eyebrow="Descriptive Wilson 95% intervals"
      >
        <div className="ratio-chart">
          {Object.entries(data.summary.methods).map(([name, m], i) => (
            <div key={name}>
              <strong style={{ color: colors[i] }}>{name}</strong>
              {(["recall", "coverage"] as const).map((key) => (
                <div className="ratio-row" key={key}>
                  <span>{key}</span>
                  <div
                    className="bar-track"
                    role="img"
                    aria-label={`${name} ${key}: ${percentage(m[key].value)}, 95% interval ${intervalText(m[key])}, denominator ${m[key].denominator}`}
                  >
                    <div
                      className="bar-fill"
                      style={{
                        width: `${(m[key].value ?? 0) * 100}%`,
                        background: colors[i],
                      }}
                    />
                    {m[key].wilson_95 ? (
                      <div
                        className="interval-line"
                        style={{
                          left: `${m[key].wilson_95[0] * 100}%`,
                          width: `${(m[key].wilson_95[1] - m[key].wilson_95[0]) * 100}%`,
                        }}
                      />
                    ) : null}
                  </div>
                  <strong>{percentage(m[key].value)}</strong>
                  <small>
                    n={m[key].denominator} · CI {intervalText(m[key])}
                  </small>
                </div>
              ))}
            </div>
          ))}
        </div>
        <p className="panel-note">
          Source: actual aggregate counts · units: proportion, 0–100%. Recall is
          conclusive-only; coverage includes known-truth abstentions. Correlated
          rows limit generalization.
        </p>
      </Panel>
      <Panel
        title="Method latency distribution"
        eyebrow={
          partial
            ? "Loaded trial-page observations"
            : "All recorded customer / phase observations"
        }
      >
        <svg
          className="latency-chart"
          viewBox="0 0 540 260"
          role="img"
          aria-label={`Actual positive latency observations on log seconds axis; ${points.map((p) => `${p.name}: n=${p.values.length}`).join(", ")}`}
        >
          <g>
            {ticks.map((t) => (
              <g key={t}>
                <line
                  className="chart-grid"
                  x1="55"
                  x2="520"
                  y1={y(t)}
                  y2={y(t)}
                />
                <text x="45" y={y(t) + 4} textAnchor="end">
                  {t.toLocaleString(undefined, { maximumFractionDigits: 5 })} s
                </text>
              </g>
            ))}
          </g>
          {points.map((point, i) => (
            <g key={point.name}>
              {point.values.map((v, j) => (
                <circle
                  key={j}
                  cx={120 + i * 165 + ((j % 7) - 3) * 2.3}
                  cy={y(v)}
                  r="3.3"
                  fill={colors[i]}
                  opacity=".7"
                >
                  <title>
                    {point.name} · {v.toFixed(5)} seconds
                  </title>
                </circle>
              ))}
              <text x={120 + i * 165} y="240" textAnchor="middle">
                {point.name}
              </text>
              <text x={120 + i * 165} y="255" textAnchor="middle">
                n={point.values.length}
              </text>
            </g>
          ))}
        </svg>
        <p className="panel-note">
          Source:{" "}
          {partial
            ? "loaded backend trial page"
            : "saved actual trial observations"}{" "}
          · seconds on a log axis · includes uncertainty outcomes. Summaries use
          all recorded rows; this chart uses the explicitly shown sample window.
        </p>
      </Panel>
      <Panel
        title="Confusion matrices"
        eyebrow="Known binary oracle truth + conclusive method predictions"
        className="wide-panel"
      >
        <div className="confusion-grid">
          {Object.entries(data.summary.methods).map(([name, m]) => (
            <div key={name} className="confusion-card">
              <h3>{name}</h3>
              <div>
                <span className="good">
                  <small>True positive</small>
                  <strong>{m.tp}</strong>
                </span>
                <span className="warn">
                  <small>False positive</small>
                  <strong>{m.fp}</strong>
                </span>
                <span className="danger">
                  <small>False negative</small>
                  <strong>{m.fn}</strong>
                </span>
                <span className="reported">
                  <small>True negative</small>
                  <strong>{m.tn}</strong>
                </span>
              </div>
              <p>
                n={m.scored_rows} scored · {m.abstained_on_binary_rows}{" "}
                known-truth abstentions
              </p>
            </div>
          ))}
        </div>
        <Table label="Latency chart numeric alternative">
          <thead>
            <tr>
              <th>Method</th>
              <th>Mean seconds</th>
              <th>Median seconds</th>
              <th>p95 seconds</th>
              <th>All-row sample count</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.summary.methods).map(([name, m]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{m.latency_seconds.mean?.toFixed(5) ?? "Undefined"}</td>
                <td>{m.latency_seconds.median?.toFixed(5) ?? "Undefined"}</td>
                <td>{m.latency_seconds.p95?.toFixed(5) ?? "Undefined"}</td>
                <td>{m.latency_seconds.n}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </div>
  );
}
