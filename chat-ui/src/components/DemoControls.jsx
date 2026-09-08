import { ArrowRight } from "lucide-react";
import styles from "./DemoControls.module.css";

export function DemoControls({ open, scenarios, targets, selectedTargetId, runningLabel, result, verification, questionRunning, error, onClose, onTargetChange, onRun, onReset, onAsk }) {
  if (!open) return null;
  const running = Boolean(runningLabel);
  return (
    <aside className={styles.drawer} role="dialog" aria-label="Demo Kontrolleri" aria-modal="false">
      <header className={styles.header}>
        <div><p>Yalnız geliştirme ortamı</p><h2>Demo Kontrolleri</h2></div>
        <button type="button" onClick={onClose} aria-label="Demo Kontrollerini kapat">×</button>
      </header>
      <label className={styles.target}>
        <span>Hedef cihaz</span>
        <select aria-label="Hedef cihaz" value={selectedTargetId} disabled={running} onChange={(event) => onTargetChange(event.target.value)}>
          {targets.map((target) => <option key={target.id} value={target.id}>{target.hostname}</option>)}
        </select>
      </label>
      <p className={styles.sectionLabel}>Senaryolar</p>
      <div className={styles.actions}>
        {scenarios.map((scenario) => (
          <button key={scenario.id} type="button" disabled={running || !scenario.supported_target_ids?.includes(selectedTargetId)} onClick={() => onRun(scenario)}>{scenario.label}</button>
        ))}
      </div>
      <button className={styles.reset} type="button" disabled={running} onClick={onReset}>Laboratuvarı sıfırla</button>
      {running ? <p className={styles.running} role="status">{runningLabel} çalıştırılıyor…</p> : null}
      {result ? (
        <section className={styles.result} aria-label="Demo sonucu" role="status">
          <h3>{result.title}</h3>
          {result.proof?.length ? result.proof.map((item) => (
            <p key={item.id}>{item.status === "passed" ? "✓" : item.status === "unavailable" ? "—" : "✕"} {item.label}</p>
          )) : (
            <>
              <p>✓ {result.snmp_state_changed ? "SNMP durumu değiştirildi" : "SNMP durumu doğrulandı"}</p>
              <p>✓ LibreNMS poll tamamlandı</p>
              <p>✓ {result.verified}</p>
            </>
          )}
          {result.example_question ? (
            <div className={styles.question}>
              <button type="button" disabled={questionRunning} aria-label={`Sormayı dene: ${result.example_question}`} onClick={() => onAsk(result.example_question, result.expected_investigation)}>
                <span><small>Sormayı dene</small><strong>{result.example_question}</strong></span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
      {verification ? (
        <section className={styles.verification} aria-label="İnceleme doğrulaması" role="status">
          <h3>İnceleme doğrulaması</h3>
          {verification.checks.map((item) => <p key={item.id}>{item.status === "passed" ? "✓" : "✕"} {item.label}</p>)}
        </section>
      ) : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </aside>
  );
}
