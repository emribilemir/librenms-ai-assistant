import { useEffect, useRef, useState } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { useAuiState } from "@assistant-ui/react";
import styles from "./PipelineReasoning.module.css";

// Interaction structure adapted from assistant-ui's official Reasoning element.
export function PipelineReasoning() {
  const part = useAuiState((state) => state.part.type === "reasoning" ? state.part : null);
  const streaming = useAuiState((state) => state.message.status?.type === "running");
  const [manualOpen, setManualOpen] = useState(null);
  const wasStreaming = useRef(streaming);
  const open = manualOpen ?? streaming;

  useEffect(() => {
    if (streaming && !wasStreaming.current) setManualOpen(null);
    wasStreaming.current = streaming;
  }, [streaming]);

  if (!part) return null;
  const lines = part.text.split("\n").filter(Boolean);

  return (
    <section className={styles.root} data-streaming={streaming || undefined}>
      <button type="button" className={styles.trigger} aria-expanded={open} onClick={() => setManualOpen(!open)}>
        <Brain size={16} strokeWidth={1.8} aria-hidden="true" />
        <span className={streaming ? styles.shimmer : undefined}>İnceleme adımları</span>
        <ChevronDown className={styles.chevron} size={16} aria-hidden="true" />
      </button>
      <div className={styles.panel} data-open={open || undefined} aria-live="polite" aria-busy={streaming}>
        <ol className={styles.steps}>
          {lines.map((line, index) => {
            const running = streaming && index === lines.length - 1;
            return <li key={`${index}-${line}`} data-running={running || undefined}><span className={styles.marker} aria-hidden="true" /><span>{line}</span></li>;
          })}
        </ol>
      </div>
    </section>
  );
}
