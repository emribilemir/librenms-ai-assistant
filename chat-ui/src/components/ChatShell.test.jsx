import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { AssistantThread } from "./AssistantThread";
import { DeleteThreadDialog } from "./DeleteThreadDialog";
import { ChatTranscript } from "./ChatTranscript";
import { ThreadDrawer } from "./ThreadDrawer";
import { ThreadList } from "./ThreadList";
import { AssistantChatStore } from "../store";
import { useLibreNmsExternalStoreRuntime } from "../runtime";

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

test("assistant-ui suggestions send the exact live-device prompt", async () => {
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
  fireEvent.click(screen.getByRole("button", { name: /a-up durumunu kontrol et/i }));

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

test("validated demo metadata opens a compact summary and JSON view from the same inspection", () => {
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
  const disclosure = screen.getByRole("button", { name: "Nasıl işlendi?" });
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
  expect(summaryTab).toHaveAttribute("aria-controls", within(panel).getByRole("tabpanel").id);
  expect(jsonTab).toHaveAttribute("tabindex", "-1");
  summaryTab.focus();
  fireEvent.keyDown(summaryTab, { key: "ArrowRight" });
  expect(jsonTab).toHaveFocus();
  expect(jsonTab).toHaveAttribute("aria-selected", "true");
  expect(panel.querySelector("pre")).toHaveTextContent(JSON.stringify(inspection, null, 2), { normalizeWhitespace: false });
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
  fireEvent.click(screen.getByRole("button", { name: "Nasıl işlendi?" }));
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
  expect(screen.getByRole("button", { name: "Nasıl işlendi?" })).toBeVisible();
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

test("assistant-ui keeps the copy action in the message layout while a validated answer is streaming", () => {
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
  expect(screen.getByRole("button", { name: "Yanıtı kopyala" })).toBeVisible();
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
  expect(disclosure).toHaveTextContent("2.06 sn");
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

test("live SSE stages appear as an expanded assistant-ui reasoning disclosure inside the assistant message", () => {
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

  expect(screen.getByRole("button", { name: /Cihazı çözümlüyor/i })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/Soruyu sınıflandırdı/)).toBeVisible();
  expect(screen.getAllByText(/Cihazı çözümlüyor/)).toHaveLength(2);
  expect(screen.queryByText("Validating…")).not.toBeInTheDocument();
});

test("validated fallback results are explicitly labelled for the operator", () => {
  render(<ChatTranscript messages={[{ id: "fallback", role: "assistant", content: "Safe evidence summary", usedFallback: true }]} />);
  expect(screen.getByText("Validated fallback result")).toBeVisible();
});
