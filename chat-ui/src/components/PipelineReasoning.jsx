import { useState } from "react";
import { ChevronDown, ListTree } from "lucide-react";
import { useAuiState } from "@assistant-ui/react";
import { ProcessingInspector } from "./ProcessingInspector";
import styles from "./PipelineReasoning.module.css";

function duration(value) {
  if (value == null) return null;
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)} sn` : `${value} ms`;
}

function progressLabel(lines) {
  const activeStep = lines.at(-1)?.replace(/ · \d+ ms$/, "") || "İşlem sürüyor";
  const labels = {
    "Soruyu sınıflandırıyor": "Soruyu sınıflandırıyor…",
    "Soruyu sınıflandırdı": "Soruyu sınıflandırdı…",
    "Cihazı çözümlüyor": "Cihaz çözümleniyor…",
    "Cihazı çözümledi": "Cihazı çözümledi…",
    "LibreNMS verisini okuyor": lines.some((line) => line.startsWith("Cihazı çözümledi"))
      ? "Cihaz çözümlendi · LibreNMS verisi okunuyor…"
      : "LibreNMS verisi okunuyor…",
    "LibreNMS verisini okudu": "LibreNMS verisini okudu…",
    "Doğrulanmış yanıtı hazırlıyor": "Yanıt hazırlanıyor…",
    "Yanıtı doğruladı": "Yanıt hazırlanıyor…",
  };
  return labels[activeStep] || `${activeStep}…`;
}

// Runtime stage events remain the only source of progress. The two variants
// keep transient status near the answer and completed details in the action row.
export function PipelineReasoning({ inspection, variant = "details" }) {
  const part = useAuiState((state) => state.message.content?.find((item) => item.type === "reasoning") || null);
  const streaming = useAuiState((state) => state.message.status?.type === "running");
  const metrics = useAuiState((state) => state.message.metadata?.custom?.metrics || null);
  const [open, setOpen] = useState(false);
  const lines = part?.text.split("\n").filter(Boolean) || [];

  if (variant === "progress") {
    if (!streaming || !lines.length) return null;
    return (
      <div className={styles.progress} data-streaming="true" data-slot="pipeline-progress">
        <span className={styles.progressStatus} role="status" aria-live="polite">
          <span className={styles.progressDot} aria-hidden="true" />
          <span className={styles.shimmer}>{progressLabel(lines)}</span>
        </span>
      </div>
    );
  }

  if (streaming || (!part && !inspection)) return null;
  const elapsedMs = metrics?.total_ms ?? lines.reduce((total, line) => total + Number(line.match(/· (\d+) ms$/)?.[1] || 0), 0);
  const elapsed = duration(elapsedMs);

  return (
    <section className={styles.root} data-slot="pipeline-reasoning">
      <button type="button" className={styles.trigger} aria-label={open ? "İşlem ayrıntılarını gizle" : "İşlem ayrıntılarını göster"} aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <ListTree size={14} strokeWidth={1.8} aria-hidden="true" />
        <span>Ayrıntılar</span>
        <ChevronDown className={styles.chevron} size={14} aria-hidden="true" />
      </button>
      <div className={styles.panel} data-open={open || undefined} hidden={!open} role="region" aria-label="İşleme ayrıntıları">
        {lines.length > 0 ? (
          <ol className={styles.steps} aria-label="Tamamlanan işlem aşamaları">
            {lines.map((line, index) => <li key={`${index}-${line}`}><span className={styles.marker} aria-hidden="true" /><span>{line}</span></li>)}
          </ol>
        ) : null}
        {(metrics?.time_to_first_token_ms != null || metrics?.time_to_first_visible_chunk_ms != null) ? (
          <div className={styles.telemetry} aria-label="Yanıt aktarım süreleri">
            {metrics.time_to_first_token_ms != null ? <span>İlk model yanıtı {duration(metrics.time_to_first_token_ms)}</span> : null}
            {metrics.time_to_first_visible_chunk_ms != null ? <span>Ekrana aktarım {duration(metrics.time_to_first_visible_chunk_ms)}</span> : null}
          </div>
        ) : null}
        <ProcessingInspector value={inspection} embedded />
      </div>
      {elapsed ? <span className={styles.duration}>{elapsed}</span> : null}
    </section>
  );
}
