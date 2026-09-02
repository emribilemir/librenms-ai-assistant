import { useId, useState } from "react";
import styles from "./RunMetrics.module.css";

const LABELS = {
  planner_ms: "Planner",
  resolver_ms: "Resolver",
  backend_ms: "LibreNMS",
  synthesis_ms: "Synthesis",
  time_to_first_token_ms: "Model TTFT",
  time_to_first_visible_chunk_ms: "Visible TTFT",
  total_ms: "Total",
};

export function RunMetrics({ metrics }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (!metrics) return null;

  return (
    <section className={styles.metrics} aria-label="System vitals">
      <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        <span>System vitals</span>
        <strong>{metrics.total_ms == null ? "Unavailable" : `${metrics.total_ms} ms total`}</strong>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <dl id={panelId}>
          {Object.entries(LABELS).map(([key, label]) => (
            <div key={key}>
              <dt>{label}<small>{key}</small></dt>
              <dd>{metrics[key] === null || metrics[key] === undefined ? "Unavailable" : `${metrics[key]} ms`}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
