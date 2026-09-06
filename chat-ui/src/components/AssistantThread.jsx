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
import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowRight, Check, ChevronDown, Copy, ExternalLink, Search, Server, Square, X } from "lucide-react";
import { PipelineReasoning } from "./PipelineReasoning";
import styles from "./AssistantThread.module.css";

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
  const ports = value.ports.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object" || positiveInteger(candidate.device_id) !== deviceId) return [];
    const row = { device_id: deviceId };
    const portId = positiveInteger(candidate.port_id);
    const ifIndex = positiveInteger(candidate.ifIndex);
    if (portId) row.port_id = portId;
    if (ifIndex) row.ifIndex = ifIndex;
    for (const [field, limit] of [["ifName", 120], ["ifDescr", 180], ["ifAlias", 180], ["admin_status", 32], ["oper_status", 32]]) {
      const safe = boundedText(candidate[field], limit);
      if (safe) row[field] = safe;
    }
    return [row];
  }).slice(0, 24);
  return ports.length ? { kind: "ports", device, ports } : null;
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

function StructuredPortResult({ result, navigationTargets }) {
  const targets = safeNavigationTargets(navigationTargets);
  const rowTargets = new Map(targets.filter((target) => target.kind === "port").map((target) => [target.entity_id, target]));
  const hostname = result.device.hostname || `Cihaz ${result.device.device_id}`;
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

function AssistantText() {
  const structuredValue = useAuiState((state) => state.message.metadata?.custom?.structuredResult);
  const structuredResult = safeStructuredPortResult(structuredValue);
  const navigationTargets = useAuiState((state) => state.message.metadata?.custom?.navigationTargets);
  if (structuredResult) return <StructuredPortResult result={structuredResult} navigationTargets={navigationTargets} />;
  return <div data-slot="assistant-answer"><MarkdownTextPrimitive smooth defer className={styles.markdown} /></div>;
}

function NavigationActions() {
  const navigationTargets = useAuiState((state) => state.message.metadata?.custom?.navigationTargets);
  const structuredValue = useAuiState((state) => state.message.metadata?.custom?.structuredResult);
  const structuredResult = safeStructuredPortResult(structuredValue);
  const targets = safeNavigationTargets(navigationTargets).filter((target) => !(structuredResult && target.kind === "port"));
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
  return (
    <MessagePrimitive.Root className={`${styles.message} ${styles.assistantMessage}`}>
      <div className={styles.assistantBody}>
        {usedFallback && <span className={styles.fallback}>Doğrulanmış güvenli yanıt</span>}
        <MessagePrimitive.Parts components={{ Text: AssistantText, Reasoning: () => null, Empty: () => null }} />
        <NavigationActions />
        <div className={styles.messageTools} role="group" aria-label="Mesaj eylemleri">
          <ActionBarPrimitive.Root className={styles.actionBar}><CopyAction /></ActionBarPrimitive.Root>
          <PipelineReasoning inspection={inspection} />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function LiveSuggestion() {
  return (
    <SuggestionPrimitive.Trigger send className={styles.suggestion}>
      <span><SuggestionPrimitive.Title className={styles.suggestionTitle} /><SuggestionPrimitive.Description className={styles.suggestionLabel} /></span>
      <ArrowRight size={16} strokeWidth={1.8} aria-hidden="true" />
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
  const inputRef = useRef(null);
  const searchRef = useRef(null);
  const [picker, setPicker] = useState({ open: false, query: "", triggerStart: null });
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
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
    const cursor = inputRef.current?.selectionStart ?? composerText.length;
    let nextText;
    if (picker.triggerStart !== null) {
      const suffix = composerText.slice(cursor).replace(/^\s+/, "");
      nextText = `${composerText.slice(0, picker.triggerStart)}${device.hostname} ${suffix}`;
    } else {
      const prefix = composerText.slice(0, cursor);
      const suffix = composerText.slice(cursor).replace(/^\s+/, "");
      const separator = prefix && !/\s$/.test(prefix) ? " " : "";
      nextText = `${prefix}${separator}${device.hostname} ${suffix}`;
    }
    aui.composer.setText(nextText);
    setSelectedDevice(device);
    setDiscoveryOpen(false);
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
  const handleComposerChange = (event) => {
    const detected = triggerAt(event.target.value, event.target.selectionStart ?? event.target.value.length);
    if (detected) {
      if (!picker.open || picker.triggerStart !== detected.start) onRequestDevices?.();
      setPicker({ open: true, query: detected.query, triggerStart: detected.start });
    } else if (picker.triggerStart !== null) {
      closePicker();
    }
  };
  const examples = Array.isArray(selectedDevice?.examples) ? selectedDevice.examples.slice(0, 3) : [];

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
      <ComposerPrimitive.Input ref={inputRef} rows={2} className={styles.input} maxLength={8000} placeholder={placeholder} submitMode="enter" aria-label="Ask LibreNMS" onChange={handleComposerChange} onKeyDown={handlePickerKey} />
      {discoveryOpen && examples.length ? (
        <section className={styles.discovery} role="region" aria-label="Bağlamsal soru örnekleri">
          <p>Düzenleyebileceğin örnek başlangıçlar</p>
          {examples.map((example) => <button type="button" key={example} onClick={() => { aui.composer.setText(example); setDiscoveryOpen(false); requestAnimationFrame(() => inputRef.current?.focus()); }}>{example}</button>)}
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
              <ComposerPrimitive.Send className={styles.primaryButton} aria-label="Soruyu sıraya ekle"><ArrowRight size={19} aria-hidden="true" /></ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(state) => !state.thread.isRunning && !state.composer.isEmpty}>
              <ComposerPrimitive.Send className={styles.primaryButton} aria-label="Soruyu gönder"><ArrowRight size={19} aria-hidden="true" /></ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(state) => !state.thread.isRunning && state.composer.isEmpty}>
              <button type="button" className={styles.primaryButton} aria-label="Bir soru yazın" disabled><ArrowRight size={19} aria-hidden="true" /></button>
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

export function AssistantThread({ canRetry, onRetry, suggestionsUnavailable, devices = [], recentDevices = [], onDeviceUsed, onRequestDevices, devicesUnavailable = false }) {
  const composerProps = { devices, recentDevices, onDeviceUsed, onRequestDevices, devicesUnavailable };
  return (
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
  );
}
