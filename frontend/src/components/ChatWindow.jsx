import { Composer } from './Composer';
import { MessageBubble } from './MessageBubble';
import { QuickReplies } from './QuickReplies';

export function ChatWindow({
  messages,
  input,
  setInput,
  isStreaming,
  isListening,
  isSpeaking,
  autoSpeak,
  voiceSupported,
  error,
  statusChips,
  onSend,
  onSpeak,
  onStartListening,
  onStopListening,
  onStopSpeaking,
  onToggleAutoSpeak,
  onRetry,
  onNewChat,
  onQuickReply,
  sessionId,
  messageListRef,
}) {
  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSend(input);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="assistant-meta">
          <span className="status-dot" aria-label="Assistant online" />
          <div>
            <p className="eyebrow">Mahindra</p>
            <h1>Mahindra Virtual Assistant</h1>
          </div>
        </div>
        <button type="button" className="new-chat-button" onClick={onNewChat}>
          New chat
        </button>
      </header>

      <QuickReplies onSelect={onQuickReply} disabled={isStreaming} />

      <main className="chat-panel">
        <div className="message-list" ref={messageListRef} aria-live="polite" aria-atomic="false">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {statusChips.length > 0 && (
            <div className="chip-row" aria-live="polite">
              {statusChips.map((chip, idx) => (
                <span key={`${chip.label}-${idx}`} className={`status-chip ${chip.type}`}>
                  {chip.label}
                </span>
              ))}
            </div>
          )}

          {isStreaming && (
            <div className="typing-row">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          )}
        </div>

        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button type="button" onClick={onRetry}>
              Retry
            </button>
          </div>
        )}

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={(event) => {
            event.preventDefault();
            onSend(input);
          }}
          disabled={isStreaming}
          isListening={isListening}
          isSpeaking={isSpeaking}
          autoSpeak={autoSpeak}
          voiceSupported={voiceSupported}
          onSpeak={() => onSpeak(input)}
          onStartListening={onStartListening}
          onStopListening={onStopListening}
          onStopSpeaking={onStopSpeaking}
          onToggleAutoSpeak={onToggleAutoSpeak}
          onKeyDown={handleKeyDown}
          onRetry={error ? onRetry : null}
        />
      </main>
    </div>
  );
}
