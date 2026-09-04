import styles from "./DemoControls.module.css";

export function DemoControls({ open, scenarios, runningLabel, result, error, onClose, onRun, onReset }) {
  if (!open) return null;
  const running = Boolean(runningLabel);
  return (
    <aside className={styles.drawer} role="dialog" aria-label="Demo Controls" aria-modal="false">
      <header className={styles.header}>
        <div><p>Development only</p><h2>Demo Controls</h2></div>
        <button type="button" onClick={onClose} aria-label="Close Demo Controls">×</button>
      </header>
      <p className={styles.target}>Target: <strong>lab-j9772a-01</strong></p>
      <div className={styles.actions}>
        {scenarios.map((scenario) => (
          <button key={scenario.id} type="button" disabled={running} onClick={() => onRun(scenario)}>{scenario.label}</button>
        ))}
      </div>
      <button className={styles.reset} type="button" disabled={running} onClick={onReset}>Reset Lab</button>
      {running ? <p className={styles.running} role="status">Running {runningLabel}…</p> : null}
      {result ? (
        <section className={styles.result} aria-label="Demo result" role="status">
          <h3>{result.title}</h3>
          <p>✓ {result.snmp_state_changed ? "SNMP state changed" : "SNMP state verified"}</p>
          <p>✓ LibreNMS poll completed</p>
          <p>✓ {result.verified}</p>
          {result.example_question ? <p className={styles.question}>Try asking:<br />“{result.example_question}”</p> : null}
        </section>
      ) : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </aside>
  );
}
