import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ChevronRight,
  MapPin,
  PanelRightOpen,
  Power,
  RotateCcw,
  Search,
  X,
  Zap,
} from "lucide-react";
import styles from "./DemoControls.module.css";

const ACTIONS = {
  "port-down": { group: "device", icon: ArrowDown, description: "Test portunu oper down durumuna getir" },
  "port-up": { group: "device", icon: ArrowUp, description: "Test portunu oper up durumuna getir" },
  "location-change": { group: "device", icon: MapPin, description: "Cihaz konumunu demo değerine geçir" },
  "device-down-up": { group: "device", icon: Power, description: "Gerçek down ve up geçişi oluştur" },
  "port-down-up-event": { group: "incident", icon: Zap, description: "Yeni bir port geçiş olayı oluştur" },
  "investigation-incident": { group: "incident", icon: Search, description: "İlişkili olay ve inceleme kanıtı oluştur" },
};

const RUNNING_COPY = {
  "port-down": "Port düşürülüyor…",
  "port-up": "Port kaldırılıyor…",
  "location-change": "Konum değiştiriliyor…",
  "device-down-up": "Cihaz geçişi oluşturuluyor…",
  "port-down-up-event": "Port olayı oluşturuluyor…",
  "investigation-incident": "İnceleme hazırlanıyor…",
  reset: "Laboratuvar başlangıca döndürülüyor…",
};

function ResultSummary({ result }) {
  const proof = Array.isArray(result.proof) ? result.proof : [];
  const event = proof.find((item) => item.id === "event" && item.status === "passed");
  const alert = proof.find((item) => item.id === "alert" && item.status === "passed");
  const poll = proof.find((item) => item.id === "poll" && item.status === "passed");
  const facts = [
    event?.event_id ? `Event #${event.event_id}` : null,
    alert?.alert_id ? `Alarm #${alert.alert_id}` : null,
    poll || result.librenms_completed ? "Poll tamamlandı" : null,
  ].filter(Boolean);

  return (
    <section className={styles.result} aria-label="Son işlem" role="status">
      <p className={styles.resultLabel}>Son işlem</p>
      <div className={styles.resultTitle}>
        <span aria-hidden="true">✓</span>
        <strong>{result.title}</strong>
      </div>
      <p className={styles.resultSummary}>{facts.length ? facts.join(" · ") : result.verified}</p>
      {proof.length ? (
        <details className={styles.details}>
          <summary>Ayrıntılar</summary>
          {proof.map((item) => (
            <p key={item.id}>
              {item.status === "passed" ? "✓" : item.status === "unavailable" ? "—" : "✕"} {item.label}
            </p>
          ))}
        </details>
      ) : null}
      {result.example_question ? (
        <button
          className={styles.ask}
          type="button"
          disabled={result.questionRunning}
          aria-label="Bu durumu AI'a sor"
          onClick={result.onAsk}
        >
          <span>Bu durumu AI&apos;a sor</span>
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      ) : null}
    </section>
  );
}

function ActionGroup({ label, scenarios, selectedTarget, running, onRun }) {
  if (!scenarios.length) return null;
  return (
    <section className={styles.group} aria-label={label}>
      <p className={styles.sectionLabel}>{label}</p>
      <div className={styles.actions}>
        {scenarios.map((scenario) => {
          const presentation = ACTIONS[scenario.id] || { icon: Activity, description: "Bounded demo aksiyonunu çalıştır" };
          const Icon = presentation.icon;
          const unsupported = !scenario.supported_target_ids?.includes(selectedTarget?.id);
          const unsupportedReason = selectedTarget?.unsupported_scenarios?.[scenario.id] || "Bu hedefte desteklenmiyor";
          return (
            <button
              key={scenario.id}
              type="button"
              aria-label={scenario.label}
              disabled={running || unsupported}
              onClick={() => onRun(scenario)}
            >
              <span className={styles.actionIcon}><Icon size={15} aria-hidden="true" /></span>
              <span className={styles.actionCopy}>
                <strong>{scenario.label}</strong>
                <small>{unsupported ? unsupportedReason : presentation.description}</small>
              </span>
              <ChevronRight className={styles.actionArrow} size={15} aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function DemoControls({ available, open, scenarios, targets, selectedTargetId, runningScenarioId, result, verification, questionRunning, error, onOpen, onClose, onTargetChange, onRun, onReset, onAsk }) {
  if (!available) return null;
  const running = Boolean(runningScenarioId);
  const deviceScenarios = scenarios.filter((scenario) => (ACTIONS[scenario.id]?.group || "incident") === "device");
  const incidentScenarios = scenarios.filter((scenario) => ACTIONS[scenario.id]?.group === "incident");
  const selectedTarget = targets.find((target) => target.id === selectedTargetId);
  const resultWithActions = result ? {
    ...result,
    questionRunning,
    onAsk: () => onAsk(result.example_question, result.expected_investigation),
  } : null;

  return (
    <>
      {!open ? (
        <button className={styles.handle} type="button" onClick={onOpen} aria-label="Demo Kontrollerini aç">
          <PanelRightOpen size={16} aria-hidden="true" />
          <span>Demo</span>
        </button>
      ) : null}
      <aside
        className={`${styles.drawer} ${open ? styles.open : ""}`}
        role="dialog"
        aria-label="Demo Kontrolleri"
        aria-modal="false"
        aria-hidden={!open}
        inert={!open}
      >
        <header className={styles.header}>
          <div><p>SNMPSim laboratuvarı</p><h2>Demo Kontrolleri</h2></div>
          <button type="button" onClick={onClose} aria-label="Demo Kontrollerini kapat"><X size={18} aria-hidden="true" /></button>
        </header>
        <label className={styles.target}>
          <span>Hedef cihaz</span>
          <select aria-label="Hedef cihaz" value={selectedTargetId} disabled={running} onChange={(event) => onTargetChange(event.target.value)}>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.hostname}{target.baseline_status === "down" ? " · baseline kapalı" : ""}
              </option>
            ))}
          </select>
          {selectedTarget?.baseline_status === "down" ? <small>Reset bu hedefi başlangıçtaki kapalı durumuna döndürür.</small> : null}
        </label>
        <ActionGroup label="Cihaz ve port" scenarios={deviceScenarios} selectedTarget={selectedTarget} running={running} onRun={onRun} />
        <ActionGroup label="Olay ve inceleme" scenarios={incidentScenarios} selectedTarget={selectedTarget} running={running} onRun={onRun} />
        {running ? <p className={styles.running} role="status">{RUNNING_COPY[runningScenarioId] || "Senaryo çalıştırılıyor…"}</p> : null}
        {resultWithActions ? <ResultSummary result={resultWithActions} /> : null}
        {verification ? (
          <section className={styles.verification} aria-label="İnceleme doğrulaması" role="status">
            <h3>İnceleme doğrulaması</h3>
            {verification.checks.map((item) => <p key={item.id}>{item.status === "passed" ? "✓" : "✕"} {item.label}</p>)}
          </section>
        ) : null}
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        <section className={styles.resetArea} aria-label="Sıfırla">
          <div><span>Sıfırla</span><small>Seçili hedefi kendi başlangıç durumuna döndür</small></div>
          <button className={styles.reset} type="button" disabled={running} onClick={onReset} aria-label="Laboratuvarı sıfırla">
            <RotateCcw size={15} aria-hidden="true" />
          </button>
        </section>
      </aside>
    </>
  );
}
