import { useEffect, useRef } from 'react';

import { ChatWindow } from './components/ChatWindow';
import { useChat } from './hooks/useChat';

function App() {
  const {
    sessionId,
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
    sendMessage,
    speakMessage,
    startListening,
    stopListening,
    stopSpeaking,
    toggleAutoSpeak,
    retry,
    startNewChat,
    handleQuickReply,
  } = useChat();

  const messageListRef = useRef(null);

  useEffect(() => {
    if (!messageListRef.current) {
      return;
    }

    messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
  }, [messages, statusChips, isStreaming]);

  return (
    <ChatWindow
      messages={messages}
      input={input}
      setInput={setInput}
      isStreaming={isStreaming}
      isListening={isListening}
      isSpeaking={isSpeaking}
      autoSpeak={autoSpeak}
      voiceSupported={voiceSupported}
      error={error}
      statusChips={statusChips}
      onSend={sendMessage}
      onSpeak={speakMessage}
      onStartListening={startListening}
      onStopListening={stopListening}
      onStopSpeaking={stopSpeaking}
      onToggleAutoSpeak={toggleAutoSpeak}
      onRetry={retry}
      onNewChat={startNewChat}
      onQuickReply={handleQuickReply}
      sessionId={sessionId}
      messageListRef={messageListRef}
    />
  );
}

export default App;
