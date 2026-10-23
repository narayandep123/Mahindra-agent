# Architecture

```mermaid
flowchart LR
    User[User] --> UI[React UI]
    UI --> API[FastAPI /api/chat (SSE)]
    API --> Agent[Agent loop\nsystem-prompt intent routing + tool calling]
    Agent --> Session[Session store]
    Agent --> LLM[Groq LLM]
    LLM --> Tools[Tool handlers]
    Tools --> ZohoClient[ZohoClient\nOAuth refresh]
    ZohoClient --> CRM[Zoho CRM\nLeads, Deals, Cases]
```

## Flow description

1. A user sends a message from the React UI.
2. The frontend posts the message to the FastAPI chat endpoint using SSE for streaming output.
3. The FastAPI route hands the request to the agent loop.
4. The agent uses the system prompt to route the user into the correct intent stage: New Lead, Pipeline, Booked, or Service.
5. The agent may call CRM or vehicle tools as needed.
6. The Groq LLM provides reasoning and natural-language responses.
7. Tool handlers call into Zoho CRM via the shared OAuth-enabled Zoho client.
8. The session store tracks message history and current conversational state for each active session.

## Key components

### Frontend

The React app renders the customer-facing chat experience and streams the live assistant output from the backend.

### API layer

FastAPI exposes the streaming chat endpoint and the session lifecycle endpoints for chatting and session reset.

### Agent loop

The agent loop is responsible for:

- appending user input to session history
- assembling context from the system prompt and session summary
- invoking the LLM with tool definitions
- handling tool calls and tool results
- streaming token-by-token assistant output back to the UI

### Session store

The in-memory session store keeps conversation history, collected values, and current stage across turns. It is attached to the agent and allows multi-turn intent routing.

### Tool layer

The tool handlers keep CRM actions structured and safe by validating inputs, handling duplicate detection, and returning consistent payloads.

### Zoho integration

The Zoho client manages access token refresh and retries automatically, reducing authentication failures during CRM calls.
