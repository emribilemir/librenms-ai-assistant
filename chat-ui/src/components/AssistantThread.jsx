import {
  ActionBarPrimitive,
  AuiIf,
  ComposerPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import styles from "./AssistantThread.module.css";

function Message({ role }) {
  const usedFallback = useAuiState(
    (state) => Boolean(state.message.metadata?.custom?.usedFallback),
  );

  return (
    <MessagePrimitive.Root className={`${styles.message} ${styles[role]}`}>
      <div className={styles.avatar} aria-hidden="true">
        {role === "user" ? "OP" : "AI"}
      </div>
      <div className={styles.messageBody}>
        <span className={styles.role}>
          {role === "user" ? "Operator" : "AI Assistant"}
        </span>
        {usedFallback && (
          <span className={styles.fallback}>Validated fallback result</span>
        )}
        <MessagePrimitive.Parts
          components={{
            Text: () => (
              <MessagePartPrimitive.Text
                component="p"
                smooth={false}
                className={styles.messageText}
              />
            ),
            Empty: () => <span className={styles.pending}>Validating…</span>,
          }}
        />
        {role === "assistant" && (
          <ActionBarPrimitive.Root className={styles.actionBar}>
            <ActionBarPrimitive.Copy
              className={styles.copy}
              aria-label="Copy response"
            >
              Copy response
            </ActionBarPrimitive.Copy>
          </ActionBarPrimitive.Root>
        )}
      </div>
    </MessagePrimitive.Root>
  );
}

const UserMessage = () => <Message role="user" />;
const AssistantMessage = () => <Message role="assistant" />;

function LiveSuggestion() {
  return (
    <SuggestionPrimitive.Trigger send className={styles.suggestion}>
      <span className={styles.suggestionArrow} aria-hidden="true">↗</span>
      <span>
        <SuggestionPrimitive.Title className={styles.suggestionTitle} />
        <SuggestionPrimitive.Description className={styles.suggestionLabel} />
      </span>
    </SuggestionPrimitive.Trigger>
  );
}

export function AssistantThread({ canRetry, onRetry, suggestionsUnavailable }) {
  return (
    <ThreadPrimitive.Root
      className={styles.thread}
      aria-label="AI Assistant conversation"
      data-assistant-ui="thread"
    >
      <ThreadPrimitive.Viewport className={styles.viewport}>
        <AuiIf condition={(state) => state.thread.isEmpty}>
          <div className={styles.empty}>
            <span className={styles.emptyIcon} aria-hidden="true">AI</span>
            <p className={styles.eyebrow}>LibreNMS · Read-only assistant</p>
            <h2>Ağında neyi inceleyelim?</h2>
            <p>Cihaz durumu, portlar, alarmlar ve olaylar hakkında canlı veriye dayalı sorular sor.</p>
            <div className={styles.suggestions}>
              <ThreadPrimitive.Suggestions>
                {() => <LiveSuggestion />}
              </ThreadPrimitive.Suggestions>
            </div>
            {suggestionsUnavailable && (
              <p className={styles.suggestionError} role="status">
                Canlı cihaz önerileri şu anda alınamıyor.
              </p>
            )}
            <small>Yanıtlar yalnız gözlemlenen LibreNMS verilerine dayanır.</small>
          </div>
        </AuiIf>
        <ThreadPrimitive.Messages
          components={{ UserMessage, AssistantMessage }}
        />
      </ThreadPrimitive.Viewport>

      <ThreadPrimitive.ViewportFooter className={styles.footer}>
        <ComposerPrimitive.Root className={styles.composer}>
          <label className={styles.label} htmlFor="investigation-question">
            Ask LibreNMS
          </label>
          <ComposerPrimitive.Input
            id="investigation-question"
            className={styles.input}
            maxLength={8000}
            placeholder="Example: Why is lab-j9775a-01 down?"
            submitMode="enter"
          />
          <div className={styles.actions}>
            <AuiIf condition={(state) => !state.thread.isRunning}>
              <ComposerPrimitive.Send className={styles.send}>
                Soruyu gönder
              </ComposerPrimitive.Send>
            </AuiIf>
            <AuiIf condition={(state) => state.thread.isRunning}>
              <ComposerPrimitive.Cancel className={styles.cancel}>
                Çalışmayı iptal et
              </ComposerPrimitive.Cancel>
            </AuiIf>
            {canRetry && (
              <button type="button" className={styles.retry} onClick={onRetry}>
                Retry failed investigation
              </button>
            )}
          </div>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.ViewportFooter>
    </ThreadPrimitive.Root>
  );
}
