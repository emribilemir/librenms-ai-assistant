import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { AssistantThread } from "./AssistantThread";
import { DeleteThreadDialog } from "./DeleteThreadDialog";
import { ChatTranscript } from "./ChatTranscript";
import { ThreadDrawer } from "./ThreadDrawer";
import { ThreadList } from "./ThreadList";
import { AssistantChatStore } from "../store";
import { useLibreNmsExternalStoreRuntime } from "../runtime";

const pickerDevices = [
  {
    hostname: "lab-up",
    status: "up",
    examples: [
      "lab-up modeli ne?",
      "lab-up'ta admin up olup oper down portlar hangileri?",
      "lab-up son 24 saatte neler olmuş?",
      "lab-up'de ne sorun var?",
      "lab-up işletim sistemi ne?",
      "lab-up ne kadar süredir açık?",
    ],
  },
  { hostname: "lab-down", status: "down", examples: [] },
  { hostname: "core-unknown", status: "unknown", examples: [] },
];

function PickerFixture({ devices = pickerDevices, onSend = jest.fn(), onRequestDevices = jest.fn() }) {
  const React = require("react");
  const [recentDevices, setRecentDevices] = React.useState([]);
  const runtimeStore = {
    messages: [],
    convertMessage: (message) => message,
    suggestions: [],
    isRunning: false,
    onNew: async (message) => onSend(message.content[0].text),
  };
  const runtime = useExternalStoreRuntime(runtimeStore);
  const onDeviceUsed = (hostname) => {
    setRecentDevices((items) => [hostname, ...items.filter((item) => item !== hostname)].slice(0, 4));
  };
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AssistantThread
        suggestionsUnavailable={false}
        devices={devices}
        recentDevices={recentDevices}
        onDeviceUsed={onDeviceUsed}
        onRequestDevices={onRequestDevices}
      />
    </AssistantRuntimeProvider>
  );
}

test("typing an at-query opens the live picker, filters hostnames, and inserts plain text without sending", () => {
  const send = jest.fn();
  render(<PickerFixture onSend={send} />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });

  fireEvent.change(composer, { target: { value: "@lab" } });

  const picker = screen.getByRole("dialog", { name: "Canlı cihaz seçici" });
  expect(within(picker).getByRole("option", { name: "lab-up Up" })).toBeVisible();
  expect(within(picker).getByRole("option", { name: "lab-down Down" })).toBeVisible();
  expect(within(picker).queryByText("core-unknown")).not.toBeInTheDocument();
  expect(within(picker).getByRole("option", { name: "lab-up Up" }).querySelector("[data-status]")).toHaveAttribute("data-status", "up");
  expect(within(picker).getByRole("option", { name: "lab-down Down" }).querySelector("[data-status]")).toHaveAttribute("data-status", "down");

  fireEvent.click(within(picker).getByRole("option", { name: "lab-up Up" }));

  expect(composer).toHaveValue("lab-up ");
  expect(screen.queryByRole("dialog", { name: "Canlı cihaz seçici" })).not.toBeInTheDocument();
  expect(send).not.toHaveBeenCalled();
});

test("a device inserted from the picker can be cleared before starting a new at-query", () => {
  render(<PickerFixture />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });

  fireEvent.click(screen.getByRole("button", { name: "Cihaz seç" }));
  fireEvent.click(screen.getByRole("option", { name: "lab-down Down" }));
  expect(composer).toHaveValue("lab-down ");

  fireEvent.change(composer, { target: { value: "" } });
  expect(composer).toHaveValue("");
  fireEvent.change(composer, { target: { value: "@lab-u" } });
  expect(composer).toHaveValue("@lab-u");
  expect(screen.getByRole("option", { name: "lab-up Up" })).toBeVisible();
});

test("the device icon opens the same picker with unknown status and keeps recent devices bounded at the top", () => {
  const requestDevices = jest.fn();
  render(<PickerFixture onRequestDevices={requestDevices} />);

  fireEvent.click(screen.getByRole("button", { name: "Cihaz seç" }));
  let picker = screen.getByRole("dialog", { name: "Canlı cihaz seçici" });
  expect(requestDevices).toHaveBeenCalledTimes(1);
  expect(within(picker).getByRole("option", { name: "core-unknown Unknown" }).querySelector("[data-status]")).toHaveAttribute("data-status", "unknown");
  fireEvent.click(within(picker).getByRole("option", { name: "lab-down Down" }));

  fireEvent.click(screen.getByRole("button", { name: "Cihaz seç" }));
  picker = screen.getByRole("dialog", { name: "Canlı cihaz seçici" });
  const recent = within(picker).getByRole("listbox", { name: "Son kullanılan cihazlar" });
  expect(within(recent).getByRole("option", { name: "lab-down Down" })).toBeVisible();
  const allDevices = within(picker).getByRole("listbox", { name: "Canlı cihazlar" });
  fireEvent.click(within(allDevices).getByRole("option", { name: "lab-up Up" }));
  fireEvent.click(screen.getByRole("button", { name: "Cihaz seç" }));
  const reordered = within(screen.getByRole("dialog", { name: "Canlı cihaz seçici" })).getByRole("listbox", { name: "Son kullanılan cihazlar" });
  expect(within(reordered).getAllByRole("option").map((option) => option.textContent)).toEqual(["lab-upUp", "lab-downDown"]);
});

test("picker supports arrow selection, Enter, and Escape without disturbing the composer submit contract", () => {
  const send = jest.fn();
  render(<PickerFixture onSend={send} />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  fireEvent.change(composer, { target: { value: "@lab" } });
  fireEvent.keyDown(composer, { key: "ArrowDown" });
  fireEvent.keyDown(composer, { key: "Enter" });

  expect(composer).toHaveValue("lab-down ");
  expect(send).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Cihaz seç" }));
  expect(screen.getByRole("dialog", { name: "Canlı cihaz seçici" })).toBeVisible();
  fireEvent.keyDown(screen.getByRole("searchbox", { name: "Cihazlarda ara" }), { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Canlı cihaz seçici" })).not.toBeInTheDocument();
});

test("contextual discovery stays collapsed and fills at most three editable examples without auto-submit", () => {
  const send = jest.fn();
  render(<PickerFixture onSend={send} />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  fireEvent.change(composer, { target: { value: "@lab-u" } });
  fireEvent.click(screen.getByRole("option", { name: "lab-up Up" }));

  const discovery = screen.getByRole("button", { name: "Neler sorabilirim?" });
  expect(discovery).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("region", { name: "Bağlamsal soru örnekleri" })).not.toBeInTheDocument();
  fireEvent.click(discovery);

  const examples = screen.getByRole("region", { name: "Bağlamsal soru örnekleri" });
  expect(within(examples).getAllByRole("button", { name: /lab-up/ })).toHaveLength(3);
  fireEvent.click(within(examples).getByRole("button", { name: "lab-up'ta admin up olup oper down portlar hangileri?" }));
  expect(composer).toHaveValue("lab-up'ta admin up olup oper down portlar hangileri?");
  expect(send).not.toHaveBeenCalled();
});

test("contextual discovery advances to the next deterministic window without repeating examples", () => {
  render(<PickerFixture />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  fireEvent.change(composer, { target: { value: "@lab-u" } });
  fireEvent.click(screen.getByRole("option", { name: "lab-up Up" }));
  fireEvent.click(screen.getByRole("button", { name: "Neler sorabilirim?" }));

  const examples = screen.getByRole("region", { name: "Bağlamsal soru örnekleri" });
  const first = within(examples).getAllByRole("button", { name: /lab-up/ }).map((button) => button.textContent);
  expect(first).toEqual([
    "lab-up modeli ne?",
    "lab-up'ta admin up olup oper down portlar hangileri?",
    "lab-up son 24 saatte neler olmuş?",
  ]);

  fireEvent.click(within(examples).getByRole("button", { name: "Başka örnekler" }));
  const second = within(examples).getAllByRole("button", { name: /lab-up/ }).map((button) => button.textContent);
  expect(second).toEqual([
    "lab-up'de ne sorun var?",
    "lab-up işletim sistemi ne?",
    "lab-up ne kadar süredir açık?",
  ]);
  expect(second).not.toEqual(expect.arrayContaining(first));
});

test("delete confirmation focuses cancel and cancellation leaves the thread intact", () => {
  const cancel = jest.fn();
  render(<DeleteThreadDialog open threadTitle="Core switch" onCancel={cancel} onConfirm={jest.fn()} />);
  const cancelButton = screen.getByRole("button", { name: "Sohbeti tut" });
  expect(cancelButton).toHaveFocus();
  fireEvent.click(cancelButton);
  expect(cancel).toHaveBeenCalledTimes(1);
});

test("delete dialog traps tab focus, closes on Escape, and restores its trigger", async () => {
  function Fixture() { const [open, setOpen] = require("react").useState(false); const trigger = require("react").useRef(null); const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current.focus()); }; return <><button ref={trigger} type="button" onClick={() => setOpen(true)}>Delete Core</button><DeleteThreadDialog open={open} threadTitle="Core" onCancel={close} onConfirm={jest.fn()} /></>; }
  render(<Fixture />);
  fireEvent.click(screen.getByRole("button", { name: "Delete Core" }));
  const cancel = screen.getByRole("button", { name: "Sohbeti tut" }); const confirm = screen.getByRole("button", { name: "Sohbeti sil" });
  fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true }); expect(confirm).toHaveFocus();
  fireEvent.keyDown(confirm, { key: "Tab" }); expect(cancel).toHaveFocus();
  fireEvent.keyDown(cancel, { key: "Escape" });
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(); await require("@testing-library/react").waitFor(() => expect(screen.getByRole("button", { name: "Delete Core" })).toHaveFocus());
});

test("narrow drawer uses named native controls with visible focus styling", () => {
  render(<ThreadDrawer open onClose={jest.fn()} onToggleCollapse={jest.fn()}><p>Thread list</p></ThreadDrawer>);
  expect(screen.getByRole("button", { name: "Sohbet geçmişini kapat" })).toBeVisible();
  expect(document.querySelector("[data-focus-visible='true']")).toBeTruthy();
});

test("desktop investigations remain in the accessibility tree when the mobile drawer is closed", () => {
  render(<ThreadDrawer open={false} onClose={jest.fn()} onToggleCollapse={jest.fn()}><p>Thread list</p></ThreadDrawer>);
  expect(screen.getByLabelText("Sohbet geçmişi")).not.toHaveAttribute("aria-hidden", "true");
});

test("closed mobile drawer removes its controls from keyboard focus", async () => {
  const listeners = new Set(); window.matchMedia = jest.fn(() => ({ matches: true, addEventListener: (_, listener) => listeners.add(listener), removeEventListener: (_, listener) => listeners.delete(listener) }));
  render(<ThreadDrawer open={false} onClose={jest.fn()} onToggleCollapse={jest.fn()}><button type="button">Saved thread</button></ThreadDrawer>);
  await Promise.resolve();
  expect(screen.getByLabelText("Sohbet geçmişi")).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryByRole("button", { name: "Saved thread" })).not.toBeInTheDocument();
});

test("assistant-ui suggestions are focusable, omit the decorative link glyph, and send the exact live-device prompt", async () => {
  const send = jest.fn();
  const suggestions = [{
    title: "a-up durumunu kontrol et",
    label: "Güncel cihaz durumu",
    prompt: "a-up cihazının mevcut durumunu göster.",
  }];
  const runtimeStore = {
    messages: [],
    convertMessage: (message) => message,
    suggestions,
    isRunning: false,
    onNew: async (message) => send(message.content[0].text),
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <AssistantThread suggestionsUnavailable={false} />
      </AssistantRuntimeProvider>
    );
  }

  render(<Fixture />);
  const suggestion = screen.getByRole("button", { name: /a-up durumunu kontrol et/i });
  suggestion.focus();
  expect(suggestion).toHaveFocus();
  expect(suggestion.querySelector("svg")).not.toBeInTheDocument();
  fireEvent.click(suggestion);

  await waitFor(() => {
    expect(send).toHaveBeenCalledWith("a-up cihazının mevcut durumunu göster.");
  });
});

test("assistant messages expose an assistant-ui copy action", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "Observed result" }],
    createdAt: new Date(),
  }];
  const runtimeStore = {
    messages,
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <AssistantThread suggestionsUnavailable={false} />
      </AssistantRuntimeProvider>
    );
  }

  render(<Fixture />);
  expect(screen.getByRole("button", { name: "Yanıtı kopyala" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Nasıl işlendi?" })).not.toBeInTheDocument();
});

test("validated demo metadata opens compact summary, JSON, and Python views from the same inspection", () => {
  const inspection = {
    planner: { request_type: "ports", intent: "device_ports" },
    resolution: { hostname: "lab-j9772a-01", device_id: 1, port_id: 2, ifIndex: 2 },
    route: "ports",
    tools: [
      { name: "get_device", args: { hostname: "lab-j9772a-01" } },
      { name: "get_ports", args: { device_id: 1 } },
    ],
    findings: [{ type: "port_admin_up_oper_down", port_id: 2, ifIndex: "2", admin_status: "up", oper_status: "down" }],
    synthesis_llm_called: false,
    navigation_targets: [{ kind: "port", label: "Port detayını aç", entity_id: 2, href: "/device/1/port/port=2" }],
  };
  const runtimeStore = {
    messages: [{
      id: "answer",
      role: "assistant",
      content: [{ type: "text", text: "Port 2 down" }],
      createdAt: new Date(),
      metadata: { custom: { inspection } },
    }],
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const disclosure = screen.getByRole("button", { name: /İşlem ayrıntıları/i });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("region", { name: "İşleme ayrıntıları" })).not.toBeInTheDocument();

  fireEvent.click(disclosure);
  const panel = screen.getByRole("region", { name: "İşleme ayrıntıları" });
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  expect(within(panel).getAllByText("ports", { selector: "dd" })).toHaveLength(2);
  expect(within(panel).getByText("device_ports")).toBeVisible();
  expect(within(panel).getByText("lab-j9772a-01")).toBeVisible();
  expect(within(panel).getByText("get_ports")).toBeVisible();
  expect(within(panel).getByText("Hayır")).toBeVisible();
  expect(within(panel).getByText("/device/1/port/port=2")).toBeVisible();
  expect(within(panel).queryByRole("link")).not.toBeInTheDocument();

  const summaryTab = within(panel).getByRole("tab", { name: "Özet" });
  const jsonTab = within(panel).getByRole("tab", { name: "JSON" });
  const pythonTab = within(panel).getByRole("tab", { name: "Python" });
  expect(summaryTab).toHaveAttribute("aria-controls", within(panel).getByRole("tabpanel").id);
  expect(jsonTab).toHaveAttribute("tabindex", "-1");
  expect(pythonTab).toHaveAttribute("tabindex", "-1");
  summaryTab.focus();
  fireEvent.keyDown(summaryTab, { key: "ArrowRight" });
  expect(jsonTab).toHaveFocus();
  expect(jsonTab).toHaveAttribute("aria-selected", "true");
  expect(panel.querySelector("pre")).toHaveTextContent(JSON.stringify(inspection, null, 2), { normalizeWhitespace: false });
  fireEvent.keyDown(jsonTab, { key: "ArrowRight" });
  expect(pythonTab).toHaveFocus();
  expect(pythonTab).toHaveAttribute("aria-selected", "true");
  expect(panel.querySelector("pre")).toHaveTextContent("'route': 'ports'");
  expect(panel.querySelector("pre")).toHaveTextContent("'synthesis_llm_called': False");
});

test("runtime demo mode off hides inspection retained on an earlier answer", () => {
  const runtimeStore = {
    messages: [{
      id: "answer",
      role: "assistant",
      content: [{ type: "text", text: "Port 2 down" }],
      createdAt: new Date(),
      metadata: { custom: { inspection: { planner: { request_type: "ports" }, route: "ports", tools: [], findings: [], navigation_targets: [] } } },
    }],
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} showInspection={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  expect(screen.queryByRole("button", { name: /İşlem ayrıntıları/i })).not.toBeInTheDocument();
});

test("malformed optional inspection sections are ignored by the frontend safety layer", () => {
  const runtimeStore = {
    messages: [{
      id: "answer",
      role: "assistant",
      content: [{ type: "text", text: "Validated" }],
      createdAt: new Date(),
      metadata: { custom: { inspection: {
        planner: null,
        resolution: "invalid",
        route: "ports",
        tools: [null, { name: 7, args: { token: "secret" } }],
        findings: "invalid",
        navigation_targets: [null],
        hidden_prompt: "do not render",
      } } },
    }],
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  fireEvent.click(screen.getByRole("button", { name: /İşlem ayrıntıları/i }));
  const panel = screen.getByRole("region", { name: "İşleme ayrıntıları" });
  expect(within(panel).getByText("ports", { selector: "dd" })).toBeVisible();
  fireEvent.click(within(panel).getByRole("tab", { name: "JSON" }));
  expect(within(panel).getByText(/"route": "ports"/, { selector: "pre" })).toBeVisible();
  expect(within(panel).queryByText(/secret|hidden_prompt/)).not.toBeInTheDocument();
});

test("the external-store bridge carries completed inspection metadata into assistant messages", () => {
  const inspection = { route: "atomic", tools: [], findings: [], synthesis_llm_called: false, navigation_targets: [] };
  const store = new AssistantChatStore({
    threads: [{ id: "a", title: "Core" }],
    selectedThreadId: "a",
    messages: { a: [{ id: "answer", role: "assistant", content: "Observed", runId: "r", inspection }] },
    runs: { a: { id: "r", status: "completed", stages: {} } },
    runHistory: { a: [] },
    drawerOpen: false,
  });

  function Fixture() {
    const runtime = useLibreNmsExternalStoreRuntime(store, "a", jest.fn(), jest.fn(), []);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  expect(screen.getByRole("button", { name: /İşlem ayrıntıları/i })).toBeVisible();
});

test("assistant messages render only validated relative LibreNMS navigation actions", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "Port 2 down" }],
    createdAt: new Date(),
    metadata: { custom: { navigationTargets: [
      { kind: "port", label: "Port detayını aç", entity_id: 41, href: "/device/7/port/port=41" },
      { kind: "device", label: "Kötü link", entity_id: 7, href: "https://evil.example/device/7" },
      { kind: "device", label: "Tutarsız kimlik", entity_id: 7, href: "/device/8" },
      { kind: "unknown", label: "Bilinmeyen", entity_id: 7, href: "/device/7" },
    ] } },
  }];
  const runtimeStore = {
    messages,
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const action = screen.getByRole("link", { name: "Port detayını aç" });
  expect(action).toHaveAttribute("href", "/device/7/port/port=41");
  expect(action).toHaveAttribute("target", "_blank");
  expect(screen.queryByRole("link", { name: "Kötü link" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Tutarsız kimlik" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Bilinmeyen" })).not.toBeInTheDocument();
});

test("structured port metadata renders semantic rows with inline verified links and no duplicate action", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "Port 2: admin=up oper=down\nPort 3: admin=down oper=down" }],
    createdAt: new Date(),
    metadata: { custom: {
      structuredResult: {
        kind: "ports",
        device: { device_id: 7, hostname: "lab-j9772a-02" },
        ports: [
          { device_id: 7, port_id: 41, ifIndex: 2, ifName: "2", ifAlias: "Test-Down", admin_status: "up", oper_status: "down" },
          { device_id: 7, port_id: 42, ifIndex: 3, ifName: "3", ifAlias: "Disabled", admin_status: "down", oper_status: "down" },
          { device_id: 7, port_id: 43, ifIndex: 4, ifName: "4", ifDescr: "Uplink", admin_status: "up", oper_status: "up" },
        ],
      },
      navigationTargets: [
        { kind: "port", label: "Port detayını aç", entity_id: 41, href: "/device/7/port/port=41" },
        { kind: "port", label: "Port detayını aç", entity_id: 42, href: "/device/7/port/port=42" },
        { kind: "port", label: "Port detayını aç", entity_id: 43, href: "/device/7/port/port=43" },
      ],
    } },
  }];
  const runtimeStore = { messages, convertMessage: (message) => message, isRunning: false, onNew: async () => {} };
  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);

  expect(screen.queryByText(/admin=up oper=down/)).not.toBeInTheDocument();
  expect(screen.getByRole("table", { name: "lab-j9772a-02 portları" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Port 2" })).toHaveAttribute("href", "/device/7/port/port=41");
  expect(screen.getByRole("link", { name: "Port 3" })).toHaveAttribute("href", "/device/7/port/port=42");
  expect(screen.getAllByRole("cell", { name: "Down" }).find((cell) => cell.dataset.status === "problem")).toBeVisible();
  expect(screen.getAllByRole("cell", { name: "Disabled" })[0]).toHaveAttribute("data-status", "neutral");
  expect(screen.getAllByRole("cell", { name: "Up" }).find((cell) => cell.dataset.status === "positive")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Port detayını aç" })).not.toBeInTheDocument();
});

test("unresolved structured port rows show only the compact device fallback action", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "fallback" }],
    createdAt: new Date(),
    metadata: { custom: {
      structuredResult: {
        kind: "ports",
        device: { device_id: 7, hostname: "lab-j9772a-02" },
        ports: [{ device_id: 7, ifIndex: 2, ifName: "2", admin_status: "up", oper_status: "down" }],
      },
      navigationTargets: [{ kind: "device", label: "LibreNMS'te cihaz portlarını aç", entity_id: 7, href: "/device/7" }],
    } },
  }];
  const runtimeStore = { messages, convertMessage: (message) => message, isRunning: false, onNew: async () => {} };
  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  expect(screen.getByText("Port 2")).not.toHaveAttribute("href");
  expect(screen.getByRole("link", { name: "LibreNMS'te cihaz portlarını aç" })).toBeVisible();
});

test("structured alert metadata renders readable severity rows and one trusted device action", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "88: Port status up/down (severity=critical, state=1)" }],
    createdAt: new Date(),
    metadata: { custom: {
      structuredResult: {
        kind: "alerts",
        device: { device_id: 7, hostname: "lab-j9772a-01" },
        alerts: [
          { device_id: 7, alert_id: 88, severity: "critical", name: "Port status up/down" },
          { device_id: 7, alert_id: 133, severity: "warning", name: "LAB - Port admin up oper down" },
          { device_id: 7, alert_id: 144, severity: "unexpected", name: "Yeni alarm" },
        ],
      },
      navigationTargets: [{ kind: "alerts", label: "Cihaz alarmlarını aç", entity_id: 7, href: "/device/7/alerts" }],
    } },
  }];
  const runtimeStore = { messages, convertMessage: (message) => message, isRunning: false, onNew: async () => {} };
  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);

  expect(screen.queryByText(/severity=critical|state=1/)).not.toBeInTheDocument();
  expect(screen.getByText("3 aktif alarm")).toBeVisible();
  expect(screen.getByRole("table", { name: "lab-j9772a-01 aktif alarmları" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "Kritik" })).toHaveAttribute("data-severity", "critical");
  expect(screen.getByRole("cell", { name: "Uyarı" })).toHaveAttribute("data-severity", "warning");
  expect(screen.getByRole("cell", { name: "Bilinmiyor" })).toHaveAttribute("data-severity", "neutral");
  expect(screen.getByRole("cell", { name: "#88" })).not.toHaveAttribute("href");
  expect(screen.getByRole("link", { name: /LibreNMS'te aç/ })).toHaveAttribute("href", "/device/7/alerts");
  expect(screen.queryByRole("link", { name: "Cihaz alarmlarını aç" })).not.toBeInTheDocument();
});

test("structured alert empty state renders no table and ignores final developer text", () => {
  const messages = [{
    id: "answer",
    role: "assistant",
    content: [{ type: "text", text: "developer fallback that must stay hidden" }],
    createdAt: new Date(),
    metadata: { custom: {
      structuredResult: { kind: "alerts", device: { device_id: 7, hostname: "lab-j9772a-01" }, alerts: [] },
      navigationTargets: [{ kind: "alerts", label: "Cihaz alarmlarını aç", entity_id: 7, href: "/device/7/alerts" }],
    } },
  }];
  const runtimeStore = { messages, convertMessage: (message) => message, isRunning: false, onNew: async () => {} };
  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);

  expect(screen.getByText("Aktif alarm bulunmuyor.")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByText("developer fallback that must stay hidden")).not.toBeInTheDocument();
});

test("completed messages place copy and one accessible details disclosure in a compact action row", () => {
  const inspection = { route: "ports", tools: [], findings: [], synthesis_llm_called: false, navigation_targets: [] };
  const messages = [{
    id: "answer", role: "assistant",
    content: [
      { type: "text", text: "Observed result" },
      { type: "reasoning", text: "Soruyu sınıflandırdı · 8 ms\nLibreNMS verisini okudu · 14 ms" },
    ],
    createdAt: new Date(),
    metadata: { custom: { metrics: { total_ms: 14500 }, inspection } },
  }];
  const runtimeStore = { messages, convertMessage: (message) => message, isRunning: false, onNew: async () => {} };
  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const actions = screen.getByRole("group", { name: "Mesaj eylemleri" });
  expect(within(actions).getByRole("button", { name: "Yanıtı kopyala" })).toBeVisible();
  const details = within(actions).getByRole("button", { name: /İşlem ayrıntıları/i });
  expect(details).not.toHaveTextContent("14.5 sn");
  expect(within(actions).getByText("14.5 sn")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Nasıl işlendi?" })).not.toBeInTheDocument();
  expect(details.nextElementSibling).toHaveAttribute("hidden");
  fireEvent.click(details);
  expect(screen.getByRole("region", { name: "İşleme ayrıntıları" })).toBeVisible();
});

test("streaming answers reserve completed message actions until the response finishes", () => {
  const runtimeStore = {
    messages: [{
      id: "answer",
      role: "assistant",
      content: [{ type: "text", text: "Observed partial result" }],
      createdAt: new Date(),
    }],
    convertMessage: (message) => message,
    isRunning: true,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  expect(screen.queryByRole("button", { name: "Yanıtı kopyala" })).not.toBeInTheDocument();
});

test("running thread keeps the composer enabled and exposes removable queued follow-ups", async () => {
  const send = jest.fn();
  const store = new AssistantChatStore({
    threads: [{ id: "a", title: "Core" }],
    selectedThreadId: "a",
    messages: { a: [{ id: "question", role: "user", content: "Çalışan soru" }] },
    runs: { a: { id: "run-a", status: "running", stages: {} } },
    runHistory: {},
    drawerOpen: false,
  });

  function Fixture() {
    const runtime = useLibreNmsExternalStoreRuntime(store, "a", send, jest.fn(), []);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  expect(composer).toBeEnabled();
  fireEvent.change(composer, { target: { value: "Bekleyen soru" } });
  fireEvent.keyDown(composer, { key: "Enter", code: "Enter" });

  expect(await screen.findByText("Bekleyen soru")).toBeVisible();
  expect(send).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Çalışmayı iptal et" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sıradaki soruyu kaldır: Bekleyen soru" }));
  expect(screen.queryByText("Bekleyen soru")).not.toBeInTheDocument();
  expect(send).not.toHaveBeenCalled();
});

test("clears the controlled composer after submitting a question", async () => {
  const send = jest.fn().mockResolvedValue(undefined);
  const store = new AssistantChatStore({
    threads: [{ id: "a", title: "Core" }],
    selectedThreadId: "a",
    messages: { a: [] },
    runs: {},
    runHistory: {},
    drawerOpen: false,
  });

  function Fixture() {
    const runtime = useLibreNmsExternalStoreRuntime(store, "a", send, jest.fn(), []);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  fireEvent.change(composer, { target: { value: "Cihaz ne durumda?" } });
  fireEvent.click(screen.getByRole("button", { name: "Soruyu gönder" }));

  await waitFor(() => expect(send).toHaveBeenCalledWith("Cihaz ne durumda?"));
  await waitFor(() => expect(composer).toHaveValue(""));
});

test("composer uses upward send iconography while preserving empty and active submit states", async () => {
  const send = jest.fn().mockResolvedValue(undefined);
  const runtimeStore = {
    messages: [],
    convertMessage: (message) => message,
    suggestions: [],
    isRunning: false,
    onNew: async (message) => send(message.content[0].text),
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const composer = screen.getByRole("textbox", { name: "Ask LibreNMS" });
  const emptyAction = screen.getByRole("button", { name: "Bir soru yazın" });
  expect(emptyAction).toBeDisabled();
  expect(emptyAction.querySelector(".lucide-arrow-up")).toBeInTheDocument();

  fireEvent.change(composer, { target: { value: "Cihaz ne durumda?" } });
  const sendAction = screen.getByRole("button", { name: "Soruyu gönder" });
  expect(sendAction).toBeEnabled();
  expect(sendAction.querySelector(".lucide-arrow-up")).toBeInTheDocument();
  fireEvent.click(sendAction);

  await waitFor(() => expect(send).toHaveBeenCalledWith("Cihaz ne durumda?"));
});

test("saved conversations are rendered and switched by assistant-ui thread-list primitives", async () => {
  const switchThread = jest.fn();
  const createThread = jest.fn();
  const runtimeStore = {
    messages: [],
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
    adapters: {
      threadList: {
        threadId: "core",
        threads: [
          { id: "core", status: "regular", title: "Core uplink" },
          { id: "edge", status: "regular", title: "Edge alarms" },
        ],
        onSwitchToThread: switchThread,
        onSwitchToNewThread: createThread,
      },
    },
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><ThreadList onDelete={jest.fn()} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  expect(document.querySelector('[data-slot="aui_thread-list-root"]')).toBeTruthy();
  expect(document.querySelector('[data-slot="aui_thread-list-item"]')).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Yeni sohbet" }));
  await waitFor(() => expect(createThread).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Edge alarms" }));
  await waitFor(() => expect(switchThread).toHaveBeenCalledWith("edge"));
});

test("completed assistant answers keep stage and timing details in one reasoning disclosure", () => {
  const runtimeStore = {
    messages: [{
      id: "answer",
      role: "assistant",
      content: [
        { type: "reasoning", text: "Soruyu sınıflandırdı · 8 ms\nCihazı çözümledi · 11 ms\nLibreNMS verisini okudu · 14 ms\nYanıtı doğruladı · 17 ms" },
        { type: "text", text: "Observed result" },
      ],
      createdAt: new Date(),
      metadata: { custom: { metrics: { planner_ms: 8, resolver_ms: 11, backend_ms: 14, synthesis_ms: 17, time_to_first_token_ms: 21, time_to_first_visible_chunk_ms: 29, total_ms: 2058 } } },
    }],
    convertMessage: (message) => message,
    isRunning: false,
    onNew: async () => {},
  };

  function Fixture() {
    const runtime = useExternalStoreRuntime(runtimeStore);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const disclosure = screen.getByRole("button", { name: /İşlem ayrıntıları/i });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(disclosure).not.toHaveTextContent("2.06 sn");
  expect(screen.getByText("2.06 sn")).toBeVisible();
  expect(screen.queryByText("Çalışma ayrıntıları")).not.toBeInTheDocument();
  fireEvent.click(disclosure);
  expect(screen.getByText("İlk model yanıtı 21 ms")).toBeVisible();
  expect(screen.getByText("Ekrana aktarım 29 ms")).toBeVisible();
});

test("completed reasoning follows the answer and its closed panel reserves no layout row", () => {
  const store = new AssistantChatStore({
    threads: [{ id: "a", title: "Ports" }],
    selectedThreadId: "a",
    messages: { a: [{ id: "answer", role: "assistant", content: "No port rows.", runId: "r" }] },
    runs: {},
    runHistory: { a: [{
      id: "r",
      status: "completed",
      stages: {
        planner: { status: "completed", durationMs: 8 },
        resolver: { status: "completed", durationMs: 11 },
        librenms: { status: "completed", durationMs: 14 },
      },
      total_ms: 33,
    }] },
    drawerOpen: false,
  });

  function Fixture() {
    const runtime = useLibreNmsExternalStoreRuntime(store, "a", jest.fn(), jest.fn(), []);
    return <AssistantRuntimeProvider runtime={runtime}><AssistantThread suggestionsUnavailable={false} /></AssistantRuntimeProvider>;
  }

  render(<Fixture />);
  const answer = screen.getByText("No port rows.").closest('[data-slot="assistant-answer"]');
  const disclosure = screen.getByRole("button", { name: /İşlem ayrıntıları/i });
  const panel = disclosure.nextElementSibling;

  expect(answer.compareDocumentPosition(disclosure) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(panel).toHaveAttribute("hidden");
  fireEvent.click(disclosure);
  expect(panel).not.toHaveAttribute("hidden");
});

test("live SSE stages replace the checklist with one compact assistant-side status", () => {
  const store = new AssistantChatStore({
    threads: [{ id: "a", title: "Core" }],
    selectedThreadId: "a",
    messages: { a: [{ id: "run-r", role: "assistant", content: "", pending: true, runId: "r" }] },
    runs: {
      a: {
        id: "r",
        status: "running",
        stages: {
          planner: { status: "completed", durationMs: 8 },
          resolver: { status: "running" },
        },
      },
    },
    runHistory: {},
    drawerOpen: false,
  });

  function Fixture() {
    const runtime = useLibreNmsExternalStoreRuntime(store, "a", jest.fn(), jest.fn(), []);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <AssistantThread suggestionsUnavailable={false} />
      </AssistantRuntimeProvider>
    );
  }

  render(<Fixture />);

  expect(screen.getByRole("status")).toHaveTextContent("Cihaz çözümleniyor…");
  expect(screen.queryByRole("button", { name: /Cihazı çözümlüyor/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/Soruyu sınıflandırdı/)).not.toBeInTheDocument();
  expect(screen.queryByText("Validating…")).not.toBeInTheDocument();
});

test("validated fallback results are explicitly labelled for the operator", () => {
  render(<ChatTranscript messages={[{ id: "fallback", role: "assistant", content: "Safe evidence summary", usedFallback: true }]} />);
  expect(screen.getByText("Validated fallback result")).toBeVisible();
});
