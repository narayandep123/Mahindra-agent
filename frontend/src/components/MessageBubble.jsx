export function MessageBubble({ message, isStreaming = false }) {
  const isUser = message.role === 'user';
  const content = typeof message.content === 'string' ? message.content.trimStart() : message.content;

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && <span className="assistant-badge">AI</span>}
      <div className={`bubble ${isUser ? 'user' : 'assistant'} ${isStreaming ? 'streaming' : ''}`}>
        {content}
        {isStreaming && <span className="cursor" aria-hidden="true">▍</span>}
      </div>
    </div>
  );
}
