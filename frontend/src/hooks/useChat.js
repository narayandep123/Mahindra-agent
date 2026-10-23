import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'mahindra-chat-session-id';

const BASE_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Hi! I can help with vehicle options, test drives, bookings, and service requests. How can I help today?',
};

function createSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useChat() {
  const [sessionId, setSessionIdState] = useState(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    return stored || null;
  });
  const [messages, setMessages] = useState([BASE_MESSAGE]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusChips, setStatusChips] = useState([]);
  const [error, setError] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState({
    recognition: false,
    synthesis: false,
  });
  const [autoSpeak, setAutoSpeak] = useState(false);
  const lastMessageRef = useRef('');
  const assistantMessageRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem(STORAGE_KEY, sessionId);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }, [sessionId]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const supportsRecognition = Boolean(SpeechRecognition);
    const supportsSynthesis = Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance);
    setVoiceSupported({ recognition: supportsRecognition, synthesis: supportsSynthesis });

    if (!supportsRecognition) {
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-IN';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
      setError('');
    };

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || '')
        .join(' ')
        .trim();

      setInput(transcript);
    };

    recognition.onerror = () => {
      setError('Voice input failed. Please try again or type your message.');
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.onstart = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognition.stop();
      recognitionRef.current = null;
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const resetConversation = useCallback(() => {
    setMessages([BASE_MESSAGE]);
    setStatusChips([]);
    setError('');
    setInput('');
    setIsStreaming(false);
    setIsListening(false);
    setIsSpeaking(false);
    assistantMessageRef.current = null;
  }, []);

  const speakMessage = useCallback(
    (text) => {
      if (!text?.trim()) {
        return;
      }

      if (!voiceSupported.synthesis || typeof window === 'undefined') {
        setError('Voice output is not supported in this browser.');
        return;
      }

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text.trim());
      utterance.lang = 'en-IN';
      utterance.rate = 1;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => {
        setIsSpeaking(false);
        setError('Voice output failed. Please try again.');
      };

      window.speechSynthesis.speak(utterance);
    },
    [voiceSupported.synthesis],
  );

  const stopSpeaking = useCallback(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      return;
    }
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const startListening = useCallback(() => {
    if (isStreaming || isListening) {
      return;
    }

    if (!voiceSupported.recognition || !recognitionRef.current) {
      setError('Voice input is not supported in this browser.');
      return;
    }

    try {
      recognitionRef.current.start();
    } catch {
      setError('Voice input is currently unavailable. Please try again.');
    }
  }, [isListening, isStreaming, voiceSupported.recognition]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current) {
      return;
    }
    recognitionRef.current.stop();
    setIsListening(false);
  }, []);

  const toggleAutoSpeak = useCallback(() => {
    setAutoSpeak((current) => !current);
  }, []);

  const ensureAssistantMessage = useCallback((text) => {
    setMessages((current) => {
      const last = current[current.length - 1];
      if (last && last.role === 'assistant' && last.id === assistantMessageRef.current) {
        return current.map((message) =>
          message.id === assistantMessageRef.current ? { ...message, content: text } : message,
        );
      }

      const generatedId = `assistant-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      assistantMessageRef.current = generatedId;
      return [...current, { id: generatedId, role: 'assistant', content: text }];
    });
  }, []);

  const sendMessage = useCallback(
    async (rawText) => {
      const trimmed = rawText.trim();
      if (!trimmed || isStreaming) {
        return;
      }

      const activeSessionId = sessionId || createSessionId();
      if (!sessionId) {
        setSessionIdState(activeSessionId);
      }

      lastMessageRef.current = trimmed;
      setInput('');
      setError('');
      setMessages((current) => [...current, { id: `user-${Date.now()}`, role: 'user', content: trimmed }]);
      setIsStreaming(true);
      assistantMessageRef.current = null;
      setStatusChips([]);

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: activeSessionId, message: trimmed }),
        });

        if (!response.ok) {
          const maybeJson = await response.clone().json().catch(() => ({}));
          throw new Error(maybeJson.error || 'The assistant is currently unavailable.');
        }

        if (!response.body) {
          throw new Error('The assistant stream is not available right now.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamText = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          let boundaryIndex;
          while ((boundaryIndex = buffer.indexOf('\n\n')) >= 0) {
            const rawEvent = buffer.slice(0, boundaryIndex).trim();
            buffer = buffer.slice(boundaryIndex + 2);

            if (!rawEvent.startsWith('data:')) {
              continue;
            }

            const payload = rawEvent.replace(/^data:\s*/, '').trim();
            if (!payload) {
              continue;
            }

            try {
              const event = JSON.parse(payload);

              if (event.type === 'token') {
                streamText += event.text || '';
                ensureAssistantMessage(streamText);
              }

              if (event.type === 'tool_start') {
                setStatusChips([{ type: 'tool', label: 'Checking CRM...' }]);
              }

              if (event.type === 'tool_end') {
                if (event.ok) {
                  setStatusChips([{ type: 'success', label: 'Saved to CRM ✓' }]);
                } else {
                  setStatusChips([{ type: 'error', label: 'CRM update failed' }]);
                }
              }

              if (event.type === 'done') {
                setStatusChips([]);
                if (autoSpeak && streamText.trim()) {
                  speakMessage(streamText);
                }
                break;
              }

              if (event.type === 'error') {
                setError(event.message || 'The assistant hit a brief problem.');
                setStatusChips([]);
                break;
              }
            } catch (jsonError) {
              console.warn('Ignoring invalid SSE payload:', payload, jsonError);
            }
          }
        }

        if (!error) {
          setStatusChips([]);
        }
      } catch (err) {
        setError(err.message || 'The assistant hit a brief problem. Please try again.');
      } finally {
        setIsStreaming(false);
      }
    },
    [autoSpeak, ensureAssistantMessage, isStreaming, sessionId, speakMessage],
  );

  const retry = useCallback(() => {
    if (!lastMessageRef.current) {
      return;
    }
    sendMessage(lastMessageRef.current);
  }, [sendMessage]);

  const startNewChat = useCallback(async () => {
    const currentId = sessionId;

    if (currentId) {
      try {
        await fetch(`/api/session/${currentId}`, { method: 'DELETE' });
      } catch (error) {
        // Ignore 404 / delete issues; the UI should still reset locally.
      }
    }

    const freshId = createSessionId();
    setSessionIdState(freshId);
    resetConversation();
    sessionStorage.setItem(STORAGE_KEY, freshId);
  }, [resetConversation, sessionId]);

  const handleQuickReply = useCallback(
    (value) => {
      setInput(value);
    },
    [],
  );

  return {
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
  };
}
