import { createContext, useContext, useMemo, useRef, useState } from "react";
import {
  ThreadListItemMorePrimitive,
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { LoaderCircle, MessageSquarePlus, MoreHorizontal, Search, Trash2 } from "lucide-react";
import styles from "./ThreadList.module.css";

// Component structure follows assistant-ui's official Thread List element.
// Styling is scoped locally so the LibreNMS host page is never reset.
const DeleteThreadContext = createContext(null);

function ThreadItem() {
  const onDelete = useContext(DeleteThreadContext);
  const thread = useAuiState((state) => state.threadListItem);
  const moreTrigger = useRef(null);

  return (
    <ThreadListItemPrimitive.Root className={styles.item} data-slot="aui_thread-list-item">
      <ThreadListItemPrimitive.Trigger className={styles.thread} data-slot="aui_thread-list-item-trigger">
        {thread.isRunning && <LoaderCircle className={styles.running} size={14} aria-hidden="true" />}
        <span className={styles.title} data-slot="aui_thread-list-item-title"><ThreadListItemPrimitive.Title fallback="Yeni sohbet" /></span>
        {thread.isRunning && <span className={styles.srOnly}>Çalışıyor</span>}
      </ThreadListItemPrimitive.Trigger>
      <ThreadListItemMorePrimitive.Root>
        <ThreadListItemMorePrimitive.Trigger ref={moreTrigger} className={styles.more} data-slot="aui_thread-list-item-more" aria-label={`${thread.title || "Yeni sohbet"} için seçenekler`}>
          <MoreHorizontal size={16} aria-hidden="true" />
        </ThreadListItemMorePrimitive.Trigger>
        <ThreadListItemMorePrimitive.Content side="right" align="start" sideOffset={6} className={styles.menu} data-slot="aui_thread-list-item-more-content">
          <ThreadListItemMorePrimitive.Item className={styles.delete} onSelect={() => {
            const target = { id: thread.id, title: thread.title || "" };
            const trigger = moreTrigger.current;
            requestAnimationFrame(() => onDelete?.(target, trigger));
          }}>
            <Trash2 size={15} aria-hidden="true" /> Sohbeti sil
          </ThreadListItemMorePrimitive.Item>
        </ThreadListItemMorePrimitive.Content>
      </ThreadListItemMorePrimitive.Root>
    </ThreadListItemPrimitive.Root>
  );
}

function FilteredItems({ query }) {
  const threadIds = useAuiState((state) => state.threads.threadIds);
  const threadItems = useAuiState((state) => state.threads.threadItems);
  const indices = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("tr");
    if (!normalized) return threadIds.map((_, index) => index);
    const byId = new Map(threadItems.map((thread) => [thread.id, thread]));
    return threadIds.flatMap((id, index) => ((byId.get(id)?.title || "Yeni sohbet").toLocaleLowerCase("tr").includes(normalized) ? [index] : []));
  }, [query, threadIds, threadItems]);

  if (query.trim() && indices.length === 0) return <p className={styles.empty}>Sohbet bulunamadı</p>;
  return indices.map((index) => (
    <ThreadListPrimitive.ItemByIndex key={threadIds[index]} index={index} components={{ ThreadListItem: ThreadItem }} />
  ));
}

export function ThreadList({ onDelete }) {
  const [query, setQuery] = useState("");
  const hasThreads = useAuiState((state) => state.threads.threadIds.length > 0);

  return (
    <DeleteThreadContext.Provider value={onDelete}>
      <nav className={styles.nav} aria-label="Kayıtlı sohbetler">
        <ThreadListPrimitive.Root className={styles.root} data-slot="aui_thread-list-root">
          <ThreadListPrimitive.New className={styles.newThread} data-slot="aui_thread-list-new">
            <MessageSquarePlus size={17} aria-hidden="true" />
            <span data-slot="aui_thread-list-new-label">Yeni sohbet</span>
          </ThreadListPrimitive.New>
          {hasThreads && <label className={styles.search} data-slot="aui_thread-list-search"><Search size={15} aria-hidden="true" /><span className={styles.srOnly}>Sohbetlerde ara</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Sohbetlerde ara" /></label>}
          <div className={styles.items} data-slot="aui_thread-list-items"><FilteredItems query={query} /></div>
        </ThreadListPrimitive.Root>
      </nav>
    </DeleteThreadContext.Provider>
  );
}
