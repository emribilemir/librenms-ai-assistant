import { useEffect, useRef, useState } from "react";
import { ChevronDown, ListTree } from "lucide-react";
import { useAuiState } from "@assistant-ui/react";
import styles from "./PipelineReasoning.module.css";

function duration(value) {
  if (value == null) return null;
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)} sn` : `${value} ms`;
}

// Interaction structure adapted from assistant-ui's official Reasoning element.
export function PipelineReasoning() {
  const part = useAuiState((state) => state.part.type === "reasoning" ? state.part : null);
  const streaming = useAuiState((state) => state.message.status?.type === "running");
  const metrics = useAuiState((state) => state.message.metadata?.custom?.metrics || null);
  const [manualOpen, setManualOpen] = useState(null);
  const wasStreaming = useRef(streaming);
  const open = manualOpen ?? streaming;

  useEffect(() => {
    if (streaming && !wasStreaming.current) setManualOpen(null);
    wasStreaming.current = streaming;
  }, [streaming]);

  if (!part) return null;
  const lines = part.text.split("\n").filter(Boolean);
  const elapsedMs = metrics?.total_ms ?? lines.reduce((total, line) => total + Number(line.match(/· (\d+) ms$/)?.[1] || 0), 0);
  const activeStep = lines.at(-1)?.replace(/ · \d+ ms$/, "") || "İşlem sürüyor";
  const label = streaming
    ? (activeStep === "Yanıtı doğruladı" ? "Yanıt aktarılıyor" : activeStep)
    : `İşlem ayrıntıları${elapsedMs ? ` · ${duration(elapsedMs)}` : ""}`;

  return (
    <section className={styles.root} data-slot="pipeline-reasoning" data-streaming={streaming || undefined}>
      <button type="button" className={styles.trigger} aria-expanded={open} onClick={() => setManualOpen(!open)}>
        <ListTree size={15} strokeWidth={1.8} aria-hidden="true" />
        <span className={streaming ? styles.shimmer : undefined}>{label}</span>
        <ChevronDown className={styles.chevron} size={16} aria-hidden="true" />
      </button>
      <div className={styles.panel} data-open={open || undefined} hidden={!open} aria-live="polite" aria-busy={streaming}>
        <ol className={styles.steps}>
          {lines.map((line, index) => {
            const running = streaming && index === lines.length - 1;
            return <li key={`${index}-${line}`} data-running={running || undefined}><span className={styles.marker} aria-hidden="true" /><span>{line}</span></li>;
          })}
        </ol>
        {!streaming && (metrics?.time_to_first_token_ms != null || metrics?.time_to_first_visible_chunk_ms != null) && (
          <div className={styles.telemetry} aria-label="Yanıt aktarım süreleri">
            {metrics.time_to_first_token_ms != null && <span>İlk model yanıtı {duration(metrics.time_to_first_token_ms)}</span>}
            {metrics.time_to_first_visible_chunk_ms != null && <span>Ekrana aktarım {duration(metrics.time_to_first_visible_chunk_ms)}</span>}
          </div>
        )}
      </div>
    </section>
  );
}
