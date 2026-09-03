import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
