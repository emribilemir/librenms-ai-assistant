import { STAGES } from "../store";
import styles from "./RunProgress.module.css";

const STAGE_COPY = {
  planner: { running: "Soruyu sınıflandırıyor", completed: "Soruyu sınıflandırdı", waiting: "Soruyu sınıflandıracak" },
  resolver: { running: "Cihazı çözümlüyor", completed: "Cihazı çözümledi", waiting: "Cihazı çözümleyecek" },
  librenms: { running: "LibreNMS verisini okuyor", completed: "LibreNMS verisini okudu", waiting: "LibreNMS verisini okuyacak" },
  synthesis: { running: "Doğrulanmış yanıtı hazırlıyor", completed: "Doğrulanmış yanıtı hazırladı", waiting: "Gerekirse yanıtı sentezleyecek" },
};

export function RunProgress({ run }) {
  if (!run || run.status !== "running") return null;
  const stages = run.stages || {};
  const announcement = STAGES.filter((stage) => stages[stage])
    .map((stage) => STAGE_COPY[stage][stages[stage].status])
    .join(", ");

  return (
    <section className={styles.rail} aria-label="Pipeline progress">
      <div className={styles.heading}><span>Live pipeline</span><strong>Gerçek zamanlı</strong></div>
      <p className={styles.live} aria-live="polite">{announcement || "Pipeline başlatılıyor"}</p>
      <ol>
        {STAGES.map((stage) => {
          const item = stages[stage];
          const status = item?.status || "waiting";
          return (
            <li key={stage} className={styles[status]}>
              <span className={styles.marker} aria-hidden="true">{status === "completed" ? "✓" : status === "running" ? "●" : "○"}</span>
              <span><b>{STAGE_COPY[stage][status]}</b><small>{stage}</small></span>
              {item?.durationMs !== undefined && <time>{item.durationMs}ms</time>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
