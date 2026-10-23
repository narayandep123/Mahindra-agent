export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  onKeyDown,
  onRetry,
  isListening,
  isSpeaking,
  autoSpeak,
  voiceSupported,
  onSpeak,
  onStartListening,
  onStopListening,
  onStopSpeaking,
  onToggleAutoSpeak,
}) {
  return (
    <div className="composer-wrap">
      <div className="voice-controls" aria-label="Voice controls">
        <button
          type="button"
          className={`voice-button ${isListening ? 'active' : ''}`}
          onClick={isListening ? onStopListening : onStartListening}
          disabled={disabled || !voiceSupported?.recognition}
          title={voiceSupported?.recognition ? 'Use microphone' : 'Voice input not supported'}
        >
          {isListening ? 'Stop mic' : 'Mic'}
        </button>

        <button
          type="button"
          className={`voice-button ${isSpeaking ? 'active' : ''}`}
          onClick={isSpeaking ? onStopSpeaking : onSpeak}
          disabled={disabled || (!isSpeaking && !value.trim()) || !voiceSupported?.synthesis}
          title={voiceSupported?.synthesis ? 'Play voice' : 'Voice output not supported'}
        >
          {isSpeaking ? 'Stop voice' : 'Speak'}
        </button>

        <button
          type="button"
          className={`voice-button ${autoSpeak ? 'active' : ''}`}
          onClick={onToggleAutoSpeak}
          disabled={!voiceSupported?.synthesis}
          title={voiceSupported?.synthesis ? 'Auto-play assistant replies' : 'Voice output not supported'}
        >
          Auto voice {autoSpeak ? 'on' : 'off'}
        </button>
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <input
          aria-label="Type your message"
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about vehicles, bookings, or service..."
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || !value.trim()}>
          {disabled ? 'Sending...' : 'Send'}
        </button>
      </form>
      {onRetry && (
        <button type="button" className="retry-link" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
