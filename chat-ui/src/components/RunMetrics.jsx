import { useId, useState } from "react";
import styles from "./RunMetrics.module.css";

const LABELS = {
  planner_ms: "Planlama",
  resolver_ms: "Cihaz eşleştirme",
  backend_ms: "LibreNMS",
  synthesis_ms: "Yanıt hazırlama",
  time_to_first_token_ms: "Model başlangıcı",
  time_to_first_visible_chunk_ms: "İlk görünür yanıt",
  total_ms: "Toplam",
};

function duration(value) {
  if (value == null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)} sn` : `${value} ms`;
}

export function RunMetrics({ metrics }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (!metrics) return null;

  return (
    <section className={styles.metrics} aria-label="Çalışma metrikleri">
      <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        <span>Çalışma ayrıntıları</span>
        <strong>{duration(metrics.total_ms)}</strong>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <dl id={panelId}>
          {Object.entries(LABELS).map(([key, label]) => (
            <div key={key}>
              <dt>{label}<small>{key}</small></dt>
              <dd>{duration(metrics[key])}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
