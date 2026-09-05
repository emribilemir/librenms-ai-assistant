import { useId, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import styles from "./ProcessingInspector.module.css";

const TOOL_ARGS = {
  list_devices: [],
  get_device: ["hostname", "device_id"],
  get_ports: ["device_id"],
  get_alerts: ["device_id"],
  get_events: ["device_id", "from_time", "to_time"],
};
const FINDING_FIELDS = ["id", "type", "time_scope", "value", "port_id", "ifIndex", "ifName", "ifAlias", "admin_status", "oper_status", "alert_id", "severity", "name", "event_id", "timestamp", "from", "to", "from_event_id", "to_event_id"];
const NAVIGATION_KINDS = new Set(["device", "port", "events", "alerts"]);

const record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const text = (value, limit = 240) => typeof value === "string" && value.length ? value.slice(0, limit) : null;
const positiveInteger = (value) => Number.isInteger(value) && value > 0 ? value : null;

function safeFields(source, fields) {
  const safe = {};
  for (const field of fields) {
    const value = source?.[field];
    if (typeof value === "string") {
      const bounded = text(value);
      if (bounded != null) safe[field] = bounded;
    } else if (typeof value === "number" && Number.isFinite(value)) {
      safe[field] = value;
    }
  }
  return safe;
}

function safeTools(value) {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const tool = record(item);
    const name = text(tool?.name, 64);
    if (!name || !(name in TOOL_ARGS)) return [];
    const args = record(tool.args);
    return [{ name, args: safeFields(args, TOOL_ARGS[name]) }];
  }).slice(0, 12);
}

function safeFindings(value) {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const finding = record(item);
    if (!finding || !text(finding.type, 64)) return [];
    const safe = safeFields(finding, FINDING_FIELDS);
    if (Array.isArray(finding.evidence_refs)) {
      const references = finding.evidence_refs.flatMap((item) => text(item, 160) ? [text(item, 160)] : []).slice(0, 6);
      if (references.length) safe.evidence_refs = references;
    }
    return [safe];
  }).slice(0, 12);
}

function safeNavigationTargets(value) {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const target = record(item);
    const kind = text(target?.kind, 32);
    const label = text(target?.label, 80);
    const entityId = positiveInteger(target?.entity_id);
    const href = text(target?.href, 240);
    if (!kind || !NAVIGATION_KINDS.has(kind) || !label || !entityId || !href?.startsWith("/")) return [];
    return [{ kind, label, entity_id: entityId, href }];
  }).slice(0, 3);
}

export function safeInspection(value) {
  const source = record(value);
  if (!source) return null;
  const safe = {};
  const planner = record(source.planner);
  const safePlanner = safeFields(planner, ["request_type", "intent"]);
  if (Object.keys(safePlanner).length) safe.planner = safePlanner;
  const resolution = record(source.resolution);
  const safeResolution = safeFields(resolution, ["hostname", "device_id", "port_id", "ifIndex"]);
  if (Object.keys(safeResolution).length) safe.resolution = safeResolution;
  const route = text(source.route, 64);
  if (route) safe.route = route;
  safe.tools = safeTools(source.tools);
  safe.findings = safeFindings(source.findings);
  if (typeof source.synthesis_llm_called === "boolean") safe.synthesis_llm_called = source.synthesis_llm_called;
  safe.navigation_targets = safeNavigationTargets(source.navigation_targets);
  return safe;
}

function SummaryField({ label, value }) {
  if (value == null || value === "") return null;
  return <div className={styles.field}><dt>{label}</dt><dd>{String(value)}</dd></div>;
}

function Summary({ inspection }) {
  const planner = inspection.planner || {};
  const resolution = inspection.resolution || {};
  return (
    <div className={styles.summary}>
      <dl className={styles.fields}>
        <SummaryField label="İstek türü" value={planner.request_type} />
        <SummaryField label="Intent" value={planner.intent} />
        <SummaryField label="Route" value={inspection.route} />
      </dl>
      {(resolution.hostname || resolution.device_id) && (
        <section className={styles.group} aria-label="Çözümlenen cihaz">
          <h4>Cihaz</h4>
          <dl className={styles.fields}>
            <SummaryField label="Hostname" value={resolution.hostname} />
            <SummaryField label="device_id" value={resolution.device_id} />
          </dl>
        </section>
      )}
      {(resolution.port_id || resolution.ifIndex) && (
        <section className={styles.group} aria-label="Çözümlenen port">
          <h4>Port</h4>
          <dl className={styles.fields}>
            <SummaryField label="ifIndex" value={resolution.ifIndex} />
            <SummaryField label="port_id" value={resolution.port_id} />
          </dl>
        </section>
      )}
      {inspection.tools.length > 0 && (
        <section className={styles.group} aria-label="Kullanılan veriler">
          <h4>Veriler</h4>
          <ul className={styles.items}>{inspection.tools.map((tool, index) => <li key={`${tool.name}-${index}`}><strong>{tool.name}</strong>{Object.keys(tool.args).length ? <code>{JSON.stringify(tool.args)}</code> : null}</li>)}</ul>
        </section>
      )}
      {inspection.findings.length > 0 && (
        <section className={styles.group} aria-label="Structured findings">
          <h4>Structured findings</h4>
          <ul className={styles.items}>{inspection.findings.map((finding, index) => {
            const details = Object.entries(finding).filter(([key]) => !["id", "type", "evidence_refs"].includes(key)).map(([key, value]) => `${key}=${value}`);
            return <li key={finding.id || `${finding.type}-${index}`}><strong>{finding.type}</strong>{details.length ? <span>{details.join(" · ")}</span> : null}</li>;
          })}</ul>
        </section>
      )}
      {inspection.navigation_targets.length > 0 && (
        <section className={styles.group} aria-label="Navigation targets">
          <h4>Navigation targets</h4>
          <ul className={styles.items}>{inspection.navigation_targets.map((target) => <li key={`${target.kind}-${target.entity_id}-${target.href}`}><strong>{target.label}</strong><code>{target.href}</code></li>)}</ul>
        </section>
      )}
      {typeof inspection.synthesis_llm_called === "boolean" && <p className={styles.synthesis}><span>LLM synthesis</span><strong>{inspection.synthesis_llm_called ? "Evet" : "Hayır"}</strong></p>}
    </div>
  );
}

export function ProcessingInspector({ value }) {
  const inspection = safeInspection(value);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("summary");
  const summaryTabRef = useRef(null);
  const jsonTabRef = useRef(null);
  const id = useId();
  if (!inspection) return null;
  const panelId = `${id}-panel`;
  const summaryTabId = `${id}-summary-tab`;
  const jsonTabId = `${id}-json-tab`;
  const tabPanelId = `${id}-tab-panel`;
  const selectTab = (nextTab) => {
    setTab(nextTab);
    (nextTab === "summary" ? summaryTabRef : jsonTabRef).current?.focus();
  };
  const handleTabKey = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    selectTab(event.key === "ArrowLeft" || event.key === "Home" ? "summary" : "json");
  };
  return (
    <section className={styles.root}>
      <button type="button" className={styles.trigger} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((current) => !current)}>
        <ChevronRight size={14} aria-hidden="true" />
        Nasıl işlendi?
      </button>
      {open && (
        <div id={panelId} className={styles.panel} role="region" aria-label="İşleme ayrıntıları">
          <div className={styles.tabs} role="tablist" aria-label="Inspector görünümü">
            <button ref={summaryTabRef} id={summaryTabId} type="button" role="tab" aria-selected={tab === "summary"} aria-controls={tabPanelId} tabIndex={tab === "summary" ? 0 : -1} onClick={() => setTab("summary")} onKeyDown={handleTabKey}>Özet</button>
            <button ref={jsonTabRef} id={jsonTabId} type="button" role="tab" aria-selected={tab === "json"} aria-controls={tabPanelId} tabIndex={tab === "json" ? 0 : -1} onClick={() => setTab("json")} onKeyDown={handleTabKey}>JSON</button>
          </div>
          <div id={tabPanelId} role="tabpanel" aria-labelledby={tab === "summary" ? summaryTabId : jsonTabId}>
            {tab === "summary" ? <Summary inspection={inspection} /> : <pre className={styles.json}>{JSON.stringify(inspection, null, 2)}</pre>}
          </div>
        </div>
      )}
    </section>
  );
}
