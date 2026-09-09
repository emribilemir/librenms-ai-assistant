import {
  ActionBarPrimitive,
  AuiIf,
  ComposerPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  QueueItemPrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowRight, ArrowUp, Check, ChevronDown, Copy, ExternalLink, Search, Server, Square, X } from "lucide-react";
import { PipelineReasoning } from "./PipelineReasoning";
import styles from "./AssistantThread.module.css";

const DemoInspectionContext = createContext(true);

// Structure adapted from assistant-ui's official Perplexity Clone example.
// Only LibreNMS-specific colors, typography and product controls are changed.
function UserText() {
  return <MessagePartPrimitive.Text component="p" className={styles.userText} />;
}

function CopyAction() {
  return (
    <ActionBarPrimitive.Copy className={styles.messageAction} aria-label="Yanıtı kopyala">
      <AuiIf condition={(state) => state.message.isCopied}><Check size={16} aria-hidden="true" /></AuiIf>
      <AuiIf condition={(state) => !state.message.isCopied}><Copy size={16} aria-hidden="true" /></AuiIf>
    </ActionBarPrimitive.Copy>
  );
}

const NAVIGATION_PATTERNS = {
  device: /^\/device\/([1-9]\d*)$/,
  port: /^\/device\/[1-9]\d*\/port\/port=([1-9]\d*)$/,
  events: /^\/device\/([1-9]\d*)\/logs\/eventlog$/,
  alerts: /^\/device\/([1-9]\d*)\/alerts$/,
};

const boundedText = (value, limit) => typeof value === "string" && value.trim() ? value.trim().slice(0, limit) : null;
const positiveInteger = (value) => Number.isInteger(value) && value > 0 ? value : null;

function safeNavigationTargets(targets) {
  if (!Array.isArray(targets)) return [];
  return targets.filter((target) => {
    if (
      !target
      || !Number.isInteger(target.entity_id)
      || target.entity_id <= 0
      || typeof target.label !== "string"
      || target.label.length === 0
      || target.label.length > 80
      || typeof target.href !== "string"
    ) return false;
    const match = NAVIGATION_PATTERNS[target.kind]?.exec(target.href);
    return Boolean(match && Number(match[1]) === target.entity_id);
  }).slice(0, 3);
}

function safeStructuredPortResult(value) {
  if (!value || value.kind !== "ports" || typeof value.device !== "object" || !Array.isArray(value.ports)) return null;
  const deviceId = positiveInteger(value.device.device_id);
  if (!deviceId) return null;
  const device = { device_id: deviceId, hostname: boundedText(value.device.hostname, 160) };
  const requestedFact = ["state", "speed", "description"].includes(value.requested_fact) ? value.requested_fact : null;
  const ports = value.ports.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object" || positiveInteger(candidate.device_id) !== deviceId) return [];
    const row = { device_id: deviceId };
    const portId = positiveInteger(candidate.port_id);
    const ifIndex = positiveInteger(candidate.ifIndex);
    const speedBps = positiveInteger(candidate.speed_bps);
    if (portId) row.port_id = portId;
    if (ifIndex) row.ifIndex = ifIndex;
    if (speedBps) row.speed_bps = speedBps;
    for (const [field, limit] of [["ifName", 120], ["ifDescr", 180], ["ifAlias", 180], ["admin_status", 32], ["oper_status", 32]]) {
      const safe = boundedText(candidate[field], limit);
      if (safe) row[field] = safe;
    }
    return [row];
  }).slice(0, 24);
  return ports.length ? { kind: "ports", device, ports, ...(requestedFact ? { requested_fact: requestedFact } : {}) } : null;
}

function safeStructuredAlertResult(value) {
  if (!value || value.kind !== "alerts" || typeof value.device !== "object" || !Array.isArray(value.alerts)) return null;
  const deviceId = positiveInteger(value.device.device_id);
  if (!deviceId) return null;
  const device = { device_id: deviceId, hostname: boundedText(value.device.hostname, 160) };
  const alerts = value.alerts.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object" || positiveInteger(candidate.device_id) !== deviceId) return [];
    const row = { device_id: deviceId };
    const alertId = positiveInteger(candidate.alert_id);
    if (alertId) row.alert_id = alertId;
    const severity = boundedText(candidate.severity, 32);
    const name = boundedText(candidate.name, 240);
    if (severity) row.severity = severity;
    if (name) row.name = name;
    return [row];
  }).slice(0, 24);
  return { kind: "alerts", device, alerts };
}

function safeStructuredEventResult(value) {
  if (!value || value.kind !== "events" || typeof value.device !== "object" || !Array.isArray(value.events)) return null;
  const deviceId = positiveInteger(value.device.device_id);
  if (!deviceId) return null;
  const device = { device_id: deviceId, hostname: boundedText(value.device.hostname, 160) };
  const events = value.events.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object" || positiveInteger(candidate.device_id) !== deviceId) return [];
    const row = { device_id: deviceId };
    const eventId = positiveInteger(candidate.event_id);
    if (eventId) row.event_id = eventId;
    for (const [field, limit] of [["timestamp", 64], ["severity", 32], ["message", 500], ["type", 80], ["reference", 120]]) {
      const safe = boundedText(candidate[field], limit);
      if (safe) row[field] = safe;
    }
    return [row];
  }).slice(0, 24);
  return { kind: "events", device, events };
}

function safeStructuredResult(value) {
  return safeStructuredPortResult(value) || safeStructuredAlertResult(value) || safeStructuredEventResult(value);
}

function titleCaseStatus(value) {
  if (value === "up") return "Up";
  if (value === "down") return "Down";
  return "Unknown";
}

function portStatus(port) {
  if (port.oper_status === "up") return { label: "Up", semantic: "positive" };
  if (port.admin_status === "down") return { label: "Disabled", semantic: "neutral" };
  if (port.admin_status === "up" && port.oper_status === "down") return { label: "Down", semantic: "problem" };
  return { label: "Unknown", semantic: "neutral" };
}

function portLabel(port) {
  return `Port ${port.ifName || port.ifIndex || port.port_id || "—"}`;
}

function formatSpeed(speedBps) {
  for (const [divisor, unit] of [[1_000_000_000, "Gbps"], [1_000_000, "Mbps"], [1_000, "Kbps"]]) {
    if (speedBps >= divisor) return `${Number((speedBps / divisor).toPrecision(6))} ${unit}`;
  }
  return `${speedBps} bps`;
}

function StructuredPortResult({ result, navigationTargets }) {
  const targets = safeNavigationTargets(navigationTargets);
  const rowTargets = new Map(targets.filter((target) => target.kind === "port").map((target) => [target.entity_id, target]));
  const hostname = result.device.hostname || `Cihaz ${result.device.device_id}`;
  const showSpeed = result.requested_fact === "speed";
  if (showSpeed) {
    return (
      <section className={styles.structuredResult} data-slot="assistant-answer">
        <p className={styles.structuredTitle}>{hostname}</p>
        <div className={styles.portFactList}>{result.ports.map((port, index) => {
          const status = portStatus(port);
          const target = port.port_id ? rowTargets.get(port.port_id) : null;
          const expectedHref = port.port_id ? `/device/${result.device.device_id}/port/port=${port.port_id}` : null;
          const label = portLabel(port);
          const context = [status.label, `Admin ${titleCaseStatus(port.admin_status)}`, port.ifAlias || port.ifDescr].filter(Boolean).join(" · ");
          return (
            <div className={styles.portFact} role="group" aria-label={`${hostname} ${label} hız bilgisi`} key={port.port_id || `${port.ifIndex || "row"}-${index}`}>
              <div className={styles.portFactHeading}>
                {target?.href === expectedHref ? <a href={target.href} target="_blank" rel="noopener noreferrer" aria-label={label}>{label}<ExternalLink size={12} aria-hidden="true" /></a> : <span>{label}</span>}
                <span>Hız</span>
              </div>
              <p className={styles.portFactValue}>{port.speed_bps ? formatSpeed(port.speed_bps) : "LibreNMS'te hız bilgisi yok."}</p>
              <p className={styles.portFactContext} data-status={status.semantic}>{context}</p>
            </div>
          );
        })}</div>
      </section>
    );
  }
  return (
    <section className={styles.structuredResult} data-slot="assistant-answer">
      <p className={styles.structuredTitle}>{hostname} portları</p>
      <table className={styles.portTable} aria-label={`${hostname} portları`}>
        <thead><tr><th>Port</th><th>Durum</th><th>Admin</th><th>Açıklama</th></tr></thead>
        <tbody>{result.ports.map((port, index) => {
          const status = portStatus(port);
          const target = port.port_id ? rowTargets.get(port.port_id) : null;
          const expectedHref = port.port_id ? `/device/${result.device.device_id}/port/port=${port.port_id}` : null;
          const label = portLabel(port);
          return (
            <tr key={port.port_id || `${port.ifIndex || "row"}-${index}`}>
              <td>{target?.href === expectedHref ? <a href={target.href} target="_blank" rel="noopener noreferrer" aria-label={label}>{label}<ExternalLink size={12} aria-hidden="true" /></a> : <span>{label}</span>}</td>
              <td data-status={status.semantic}>{status.label}</td>
              <td>{titleCaseStatus(port.admin_status)}</td>
              <td>{port.ifAlias || port.ifDescr || "—"}</td>
            </tr>
          );
        })}</tbody>
      </table>
    </section>
  );
}

const ALERT_SEVERITIES = {
  critical: { label: "Kritik", semantic: "critical" },
  danger: { label: "Kritik", semantic: "critical" },
  error: { label: "Hata", semantic: "critical" },
  major: { label: "Yüksek", semantic: "critical" },
  warning: { label: "Uyarı", semantic: "warning" },
  minor: { label: "Düşük", semantic: "warning" },
  notice: { label: "Bildirim", semantic: "info" },
  info: { label: "Bilgi", semantic: "info" },
  ok: { label: "Normal", semantic: "positive" },
  normal: { label: "Normal", semantic: "positive" },
};

function alertSeverity(value) {
  return ALERT_SEVERITIES[value?.toLocaleLowerCase("en-US")] || { label: "Bilinmiyor", semantic: "neutral" };
}

function StructuredAlertResult({ result, navigationTargets }) {
  const targets = safeNavigationTargets(navigationTargets);
  const expectedHref = `/device/${result.device.device_id}/alerts`;
  const target = targets.find((candidate) => candidate.kind === "alerts" && candidate.entity_id === result.device.device_id && candidate.href === expectedHref);
  const hostname = result.device.hostname || `Cihaz ${result.device.device_id}`;
  return (
    <section className={styles.structuredResult} data-slot="assistant-answer">
      <div className={styles.alertHeading}>
        <div>
          <p className={styles.structuredTitle}>{hostname}</p>
          {result.alerts.length ? <p className={styles.alertCount}>{result.alerts.length} aktif alarm</p> : null}
        </div>
        {target ? <a className={styles.inlineResultAction} href={target.href} target="_blank" rel="noopener noreferrer">LibreNMS'te aç<ExternalLink size={12} aria-hidden="true" /></a> : null}
      </div>
      {result.alerts.length ? (
        <table className={`${styles.portTable} ${styles.alertTable}`} aria-label={`${hostname} aktif alarmları`}>
          <thead><tr><th>Seviye</th><th>Alarm</th><th>ID</th></tr></thead>
          <tbody>{result.alerts.map((alert, index) => {
            const severity = alertSeverity(alert.severity);
            return (
              <tr key={alert.alert_id || `${alert.name || "alert"}-${index}`}>
                <td data-severity={severity.semantic}>{severity.label}</td>
                <td>{alert.name || "Adı belirtilmemiş alarm"}</td>
                <td>{alert.alert_id ? `#${alert.alert_id}` : "—"}</td>
              </tr>
            );
          })}</tbody>
        </table>
      ) : <p className={styles.alertEmpty}>Aktif alarm bulunmuyor.</p>}
    </section>
  );
}

function eventSeverity(value) {
  const numeric = /^\d+$/.test(value || "") ? Number(value) : null;
  if (numeric !== null) {
    if (numeric >= 3) return { label: `Seviye ${numeric}`, semantic: "critical" };
    if (numeric === 2) return { label: "Seviye 2", semantic: "warning" };
    return { label: `Seviye ${numeric}`, semantic: "info" };
  }
  return alertSeverity(value);
}

function formatEventTimestamp(value) {
  if (!value) return "Zaman bilgisi yok";
  const simple = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(value);
  if (simple) {
    const [, year, month, day, hour, minute, second = "00"] = simple;
    const monthNames = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
    const monthLabel = monthNames[Number(month) - 1];
    if (monthLabel) return `${Number(day)} ${monthLabel} ${year} ${hour}:${minute}:${second}`;
  }
  return value;
}

function EventMessage({ message }) {
  const transition = /^ifOperStatus:\s*(up|down)\s*->\s*(up|down)$/i.exec(message || "");
  if (!transition) return <p className={styles.eventMessage}>{message || "Mesaj belirtilmemiş"}</p>;
  const from = transition[1].toLowerCase();
  const to = transition[2].toLowerCase();
  return (
    <div className={styles.eventTransition} aria-label={`ifOperStatus ${from} durumundan ${to} durumuna geçti`}>
      <span>ifOperStatus</span>
      <strong data-state={from}>{from.toUpperCase()}</strong>
      <ArrowRight size={13} aria-hidden="true" />
      <strong data-state={to}>{to.toUpperCase()}</strong>
    </div>
  );
}

function StructuredEventResult({ result, navigationTargets }) {
  const targets = safeNavigationTargets(navigationTargets);
  const expectedHref = `/device/${result.device.device_id}/logs/eventlog`;
  const target = targets.find((candidate) => candidate.kind === "events" && candidate.entity_id === result.device.device_id && candidate.href === expectedHref);
  const hostname = result.device.hostname || `Cihaz ${result.device.device_id}`;
  return (
    <section className={styles.structuredResult} data-slot="assistant-answer">
      <div className={styles.eventHeading}>
        <div>
          <p className={styles.structuredTitle}>{hostname}</p>
          {result.events.length ? <p className={styles.eventCount}>{result.events.length} event</p> : null}
        </div>
        {target ? <a className={styles.inlineResultAction} href={target.href} target="_blank" rel="noopener noreferrer">LibreNMS'te aç<ExternalLink size={12} aria-hidden="true" /></a> : null}
      </div>
      {result.events.length ? (
        <ol className={styles.eventList} aria-label={`${hostname} eventleri`}>
          {result.events.map((event, index) => {
            const severity = eventSeverity(event.severity);
            return (
              <li key={event.event_id || `${event.timestamp || "event"}-${index}`}>
                <div className={styles.eventMeta}>
                  <time>{formatEventTimestamp(event.timestamp)}</time>
                  <span data-severity={severity.semantic}>{severity.label}</span>
                  {event.event_id ? <span>#{event.event_id}</span> : null}
                </div>
                <EventMessage message={event.message} />
              </li>
            );
          })}
        </ol>
      ) : <p className={styles.alertEmpty}>Event bulunmuyor.</p>}
    </section>
  );
}

function AssistantText() {
  const structuredValue = useAuiState((state) => state.message.metadata?.custom?.structuredResult);
  const structuredResult = safeStructuredResult(structuredValue);
  const navigationTargets = useAuiState((state) => state.message.metadata?.custom?.navigationTargets);
  if (structuredResult?.kind === "ports") return <StructuredPortResult result={structuredResult} navigationTargets={navigationTargets} />;
  if (structuredResult?.kind === "alerts") return <StructuredAlertResult result={structuredResult} navigationTargets={navigationTargets} />;
  if (structuredResult?.kind === "events") return <StructuredEventResult result={structuredResult} navigationTargets={navigationTargets} />;
  return <div data-slot="assistant-answer"><MarkdownTextPrimitive smooth defer className={styles.markdown} /></div>;
}

function NavigationActions() {
  const navigationTargets = useAuiState((state) => state.message.metadata?.custom?.navigationTargets);
  const structuredValue = useAuiState((state) => state.message.metadata?.custom?.structuredResult);
  const structuredResult = safeStructuredResult(structuredValue);
  const targets = safeNavigationTargets(navigationTargets).filter((target) => !(
    (structuredResult?.kind === "ports" && target.kind === "port")
    || (structuredResult?.kind === "alerts" && target.kind === "alerts")
    || (structuredResult?.kind === "events" && target.kind === "events")
  ));
  if (!targets.length) return null;
  return (
    <nav className={styles.navigationActions} aria-label="LibreNMS bağlantıları">
      {targets.map((target) => (
        <a key={`${target.kind}-${target.entity_id}-${target.href}`} className={styles.navigationAction} href={target.href} target="_blank" rel="noopener noreferrer">
          {target.label}<ExternalLink size={13} aria-hidden="true" />
        </a>
      ))}
    </nav>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className={`${styles.message} ${styles.userMessage}`}>
      <div className={styles.userBubble}><MessagePrimitive.Parts components={{ Text: UserText }} /></div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const usedFallback = useAuiState((state) => Boolean(state.message.metadata?.custom?.usedFallback));
  const inspection = useAuiState((state) => state.message.metadata?.custom?.inspection);
  const streaming = useAuiState((state) => state.message.status?.type === "running");
  const showInspection = useContext(DemoInspectionContext);
  return (
    <MessagePrimitive.Root className={`${styles.message} ${styles.assistantMessage}`}>
      <div className={styles.assistantBody}>
        {usedFallback && <span className={styles.fallback}>Doğrulanmış güvenli yanıt</span>}
        <PipelineReasoning inspection={showInspection ? inspection : null} variant="progress" />
        <MessagePrimitive.Parts components={{ Text: AssistantText, Reasoning: () => null, Empty: () => null }} />
        <NavigationActions />
        {!streaming ? (
          <div className={styles.messageTools} role="group" aria-label="Mesaj eylemleri">
            <ActionBarPrimitive.Root className={styles.actionBar}><CopyAction /></ActionBarPrimitive.Root>
            <PipelineReasoning inspection={showInspection ? inspection : null} variant="details" />
          </div>
        ) : null}
      </div>
    </MessagePrimitive.Root>
  );
}

function LiveSuggestion() {
  return (
    <SuggestionPrimitive.Trigger send className={styles.suggestion}>
      <span><SuggestionPrimitive.Title className={styles.suggestionTitle} /><SuggestionPrimitive.Description className={styles.suggestionLabel} /></span>
    </SuggestionPrimitive.Trigger>
  );
}

function ComposerQueue() {
  const count = useAuiState((state) => state.composer.queue.length);
  if (count === 0) return null;
  return (
    <section className={styles.queue} aria-label="Sıradaki sorular" aria-live="polite">
      <p className={styles.queueCount}>{count} sırada</p>
      <ComposerPrimitive.Queue>
        {({ queueItem }) => (
          <div className={styles.queueItem}>
            <QueueItemPrimitive.Text className={styles.queueText} />
            <QueueItemPrimitive.Remove className={styles.queueRemove} aria-label={`Sıradaki soruyu kaldır: ${queueItem.prompt}`}>
              <X size={15} aria-hidden="true" />
            </QueueItemPrimitive.Remove>
          </div>
        )}
      </ComposerPrimitive.Queue>
    </section>
  );
}

const safeDeviceStatus = (status) => status === "up" || status === "down" ? status : "unknown";
const deviceStatusLabel = (status) => status === "up" ? "Up" : status === "down" ? "Down" : "Unknown";

function DeviceOption({ device, active, onSelect }) {
  const status = safeDeviceStatus(device.status);
  const label = deviceStatusLabel(status);
  return (
    <li>
      <button type="button" role="option" aria-selected={active} className={styles.deviceOption} data-active={active || undefined} onClick={() => onSelect(device)}>
        <span className={styles.deviceName}>{device.hostname}</span>
        <span className={styles.deviceStatus}><span className={styles.statusDot} data-status={status} aria-hidden="true" />{label}</span>
      </button>
    </li>
  );
}

function triggerAt(text, cursor) {
  const beforeCursor = text.slice(0, cursor);
  const match = beforeCursor.match(/(?:^|\s)@([^\s@]*)$/);
  if (!match) return null;
  return { start: beforeCursor.lastIndexOf("@"), query: match[1] };
}

function Composer({ placeholder, canRetry, onRetry, devices = [], recentDevices = [], onDeviceUsed, onRequestDevices, devicesUnavailable }) {
  const aui = useAui();
  const composerText = useAuiState((state) => state.composer.text);
  const threadIsRunning = useAuiState((state) => state.thread.isRunning);
  const [inputText, setInputText] = useState(composerText);
  const inputOwnedRef = useRef(false);
  const inputRef = useRef(null);
  const searchRef = useRef(null);
  const [picker, setPicker] = useState({ open: false, query: "", triggerStart: null });
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [discoveryRotation, setDiscoveryRotation] = useState(0);
  useEffect(() => {
    if (composerText === inputText) return;
    if (inputOwnedRef.current && !(threadIsRunning && composerText === "")) {
      aui.composer.setText(inputText);
      return;
    }
    inputOwnedRef.current = false;
    setInputText(composerText);
  }, [aui, composerText, inputText, threadIsRunning]);
  const commitComposerText = (value) => {
    inputOwnedRef.current = true;
    setInputText(value);
    aui.composer.setText(value);
  };
  const clearSubmittedText = () => {
    const submittedText = inputText;
    queueMicrotask(() => {
      if (inputRef.current?.value !== submittedText) return;
      inputOwnedRef.current = false;
      setInputText("");
      aui.composer.setText("");
    });
  };
  const filteredDevices = useMemo(() => {
    const query = picker.query.trim().toLocaleLowerCase("tr-TR");
    return devices.filter((device) => !query || device.hostname.toLocaleLowerCase("tr-TR").includes(query));
  }, [devices, picker.query]);
  const recentRows = useMemo(() => {
    const byHostname = new Map(devices.map((device) => [device.hostname, device]));
    return recentDevices.flatMap((hostname) => byHostname.has(hostname) ? [byHostname.get(hostname)] : []);
  }, [devices, recentDevices]);
  useEffect(() => { setActiveIndex(0); }, [picker.query, devices]);

  const closePicker = () => setPicker((current) => ({ ...current, open: false }));
  const openPicker = (triggerStart = null, query = "", focusSearch = false) => {
    setPicker({ open: true, query, triggerStart });
    setActiveIndex(0);
    onRequestDevices?.();
    if (focusSearch) requestAnimationFrame(() => searchRef.current?.focus());
  };
  const selectDevice = (device) => {
    const cursor = inputRef.current?.selectionStart ?? inputText.length;
    let nextText;
    if (picker.triggerStart !== null) {
      const suffix = inputText.slice(cursor).replace(/^\s+/, "");
      nextText = `${inputText.slice(0, picker.triggerStart)}${device.hostname} ${suffix}`;
    } else {
      const prefix = inputText.slice(0, cursor);
      const suffix = inputText.slice(cursor).replace(/^\s+/, "");
      const separator = prefix && !/\s$/.test(prefix) ? " " : "";
      nextText = `${prefix}${separator}${device.hostname} ${suffix}`;
    }
    commitComposerText(nextText);
    setSelectedDevice(device);
    setDiscoveryOpen(false);
    setDiscoveryRotation(0);
    closePicker();
    onDeviceUsed?.(device.hostname);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      const position = nextText.length;
      inputRef.current?.setSelectionRange(position, position);
    });
  };
  const handlePickerKey = (event) => {
    if (!picker.open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closePicker();
      requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!filteredDevices.length) return;
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((index) => (index + direction + filteredDevices.length) % filteredDevices.length);
      return;
    }
    if (event.key === "Enter" && filteredDevices[activeIndex]) {
      event.preventDefault();
      event.stopPropagation();
      selectDevice(filteredDevices[activeIndex]);
    }
  };
  const handleComposerKeyDown = (event) => {
    handlePickerKey(event);
    if (
      !event.defaultPrevented
      && event.key === "Enter"
      && !event.shiftKey
      && !event.nativeEvent?.isComposing
      && inputText.trim()
    ) clearSubmittedText();
  };
  const handleComposerChange = (event) => {
    const value = event.target.value;
    const cursor = event.target.selectionStart ?? value.length;
    // assistant-ui composes this callback before its own controlled-input
    // update. Persist the browser value before picker state can re-render the
    // textarea and restore the previous device selection.
    commitComposerText(value);
    const detected = triggerAt(value, cursor);
    if (detected) {
      if (!picker.open || picker.triggerStart !== detected.start) onRequestDevices?.();
      setPicker({ open: true, query: detected.query, triggerStart: detected.start });
    } else if (picker.triggerStart !== null) {
      closePicker();
    }
  };
  const handleComposerInputCapture = (event) => {
    // Browser automation, paste, and replacement edits can reach the native
    // input event before assistant-ui publishes its composer snapshot. Own
    // that value during capture so an unrelated runtime refresh cannot put
    // the previously selected device back into the textarea.
    commitComposerText(event.currentTarget.value);
  };
  const examplePool = Array.isArray(selectedDevice?.examples) ? selectedDevice.examples : [];
  const exampleStart = discoveryRotation * 3;
  const examples = examplePool.slice(exampleStart, exampleStart + 3);
  const canRotateExamples = examplePool.length > 3;
  const rotateExamples = () => setDiscoveryRotation((rotation) => (
    (rotation + 1) * 3 >= examplePool.length ? 0 : rotation + 1
  ));

  return (
    <ComposerPrimitive.Root className={styles.composer}>
      <ComposerQueue />
      {picker.open ? (
        <div className={styles.devicePicker} role="dialog" aria-label="Canlı cihaz seçici">
          <div className={styles.pickerHeader}>
            <span>Canlı cihazlar</span>
            <button type="button" className={styles.pickerClose} onClick={closePicker} aria-label="Cihaz seçiciyi kapat"><X size={15} aria-hidden="true" /></button>
          </div>
          <label className={styles.deviceSearch}>
            <Search size={14} aria-hidden="true" />
            <span className={styles.srOnly}>Cihazlarda ara</span>
            <input ref={searchRef} type="search" aria-label="Cihazlarda ara" value={picker.query} onChange={(event) => setPicker((current) => ({ ...current, query: event.target.value }))} onKeyDown={handlePickerKey} placeholder="Hostname ara…" />
          </label>
          {!picker.query && recentRows.length ? (
            <section className={styles.deviceSection}>
              <p>Son kullanılanlar</p>
              <ul role="listbox" aria-label="Son kullanılan cihazlar">
                {recentRows.map((device) => <DeviceOption key={`recent-${device.hostname}`} device={device} active={false} onSelect={selectDevice} />)}
              </ul>
            </section>
          ) : null}
          <section className={styles.deviceSection}>
            <p>Cihazlar <span>{filteredDevices.length}</span></p>
            {filteredDevices.length ? (
              <ul role="listbox" aria-label="Canlı cihazlar">
                {filteredDevices.map((device, index) => <DeviceOption key={device.hostname} device={device} active={index === activeIndex} onSelect={selectDevice} />)}
              </ul>
            ) : <p className={styles.deviceEmpty}>{devicesUnavailable ? "Canlı cihaz listesi alınamıyor." : "Eşleşen canlı cihaz yok."}</p>}
          </section>
        </div>
      ) : null}
      <ComposerPrimitive.Input ref={inputRef} value={inputText} rows={2} className={styles.input} maxLength={8000} placeholder={placeholder} submitMode="enter" aria-label="Ask LibreNMS" onInputCapture={handleComposerInputCapture} onChange={handleComposerChange} onKeyDown={handleComposerKeyDown} />
      {discoveryOpen && examples.length ? (
        <section className={styles.discovery} role="region" aria-label="Bağlamsal soru örnekleri">
          <p>Düzenleyebileceğin örnek başlangıçlar</p>
          {examples.map((example) => <button type="button" key={example} onClick={() => { commitComposerText(example); setDiscoveryOpen(false); requestAnimationFrame(() => inputRef.current?.focus()); }}>{example}</button>)}
          {canRotateExamples ? <button type="button" className={styles.discoveryMore} onClick={rotateExamples}>Başka örnekler</button> : null}
        </section>
      ) : null}
      <div className={styles.composerBar}>
        <div className={styles.composerTools}>
          <span className={styles.liveMode}><Activity size={14} aria-hidden="true" /> Canlı LibreNMS</span>
          <button type="button" className={styles.deviceTrigger} aria-label="Cihaz seç" aria-expanded={picker.open} onClick={() => openPicker(null, "", true)}><Server size={15} aria-hidden="true" /></button>
          {examples.length ? <button type="button" className={styles.discoveryTrigger} aria-expanded={discoveryOpen} onClick={() => setDiscoveryOpen((open) => !open)}>Neler sorabilirim?</button> : null}
        </div>
        <div className={styles.composerActions}>
          {canRetry && <button type="button" className={styles.retry} onClick={onRetry}>Yeniden dene</button>}
          <span className={styles.primaryAction}>
            <AuiIf condition={(state) => state.thread.isRunning}>
              <ComposerPrimitive.Cancel className={`${styles.primaryButton} ${styles.stopButton}`} aria-label="Çalışmayı iptal et"><Square size={13} fill="currentColor" aria-hidden="true" /></ComposerPrimitive.Cancel>
            </AuiIf>
            <AuiIf condition={(state) => state.thread.isRunning && !state.composer.isEmpty}>
              <ComposerPrimitive.Send className={styles.primaryButton} aria-label="Soruyu sıraya ekle" onClick={clearSubmittedText}><ArrowUp size={19} aria-hidden="true" /></ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(state) => !state.thread.isRunning && !state.composer.isEmpty}>
              <ComposerPrimitive.Send className={styles.primaryButton} aria-label="Soruyu gönder" onClick={clearSubmittedText}><ArrowUp size={19} aria-hidden="true" /></ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(state) => !state.thread.isRunning && state.composer.isEmpty}>
              <button type="button" className={styles.primaryButton} aria-label="Bir soru yazın" disabled><ArrowUp size={19} aria-hidden="true" /></button>
            </AuiIf>
          </span>
        </div>
      </div>
    </ComposerPrimitive.Root>
  );
}

function EmptyState({ suggestionsUnavailable, canRetry, onRetry, composerProps }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyInner}>
        <div className={styles.wordmark}><span>LibreNMS</span> Assistant</div>
        <h2>Ağında neyi inceleyelim?</h2>
        <p className={styles.intro}>Cihaz, port, alarm ve olay verilerini canlı LibreNMS kayıtlarından araştır.</p>
        <Composer placeholder="Ağın hakkında bir soru sor…" canRetry={canRetry} onRetry={onRetry} {...composerProps} />
        <div className={styles.suggestions} aria-label="Canlı cihaz önerileri"><ThreadPrimitive.Suggestions>{() => <LiveSuggestion />}</ThreadPrimitive.Suggestions></div>
        {suggestionsUnavailable && <p className={styles.suggestionError} role="status">Canlı cihaz önerileri şu anda alınamıyor.</p>}
      </div>
    </div>
  );
}

export function AssistantThread({ canRetry, onRetry, suggestionsUnavailable, devices = [], recentDevices = [], onDeviceUsed, onRequestDevices, devicesUnavailable = false, showInspection = true }) {
  const composerProps = { devices, recentDevices, onDeviceUsed, onRequestDevices, devicesUnavailable };
  return (
    <DemoInspectionContext.Provider value={showInspection}>
    <ThreadPrimitive.Root className={styles.thread} aria-label="AI Assistant sohbeti" data-assistant-ui="thread" style={{ "--thread-max-width": "54rem" }}>
      <AuiIf condition={(state) => state.thread.isEmpty}><EmptyState suggestionsUnavailable={suggestionsUnavailable} canRetry={canRetry} onRetry={onRetry} composerProps={composerProps} /></AuiIf>
      <AuiIf condition={(state) => !state.thread.isEmpty}>
        <ThreadPrimitive.Viewport className={styles.viewport} data-slot="thread-viewport">
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
          <ThreadPrimitive.ViewportFooter className={styles.footer}>
            <ThreadPrimitive.ScrollToBottom className={styles.scrollToBottom} aria-label="En yeni mesaja git"><ChevronDown size={17} aria-hidden="true" /></ThreadPrimitive.ScrollToBottom>
            <Composer placeholder="Devam sorusu sor…" canRetry={canRetry} onRetry={onRetry} {...composerProps} />
            <p className={styles.disclaimer}>Yalnızca salt-okunur LibreNMS verileri kullanılır.</p>
          </ThreadPrimitive.ViewportFooter>
        </ThreadPrimitive.Viewport>
      </AuiIf>
    </ThreadPrimitive.Root>
    </DemoInspectionContext.Provider>
  );
}
