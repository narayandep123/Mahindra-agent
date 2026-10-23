# Automotive AI Assistant

A full-stack automotive customer-assistant monorepo built with a FastAPI backend and a React + Vite frontend. The product helps customers with vehicle discovery, lead intake, deal follow-up, booking status, and service requests using a Groq-backed agent and Zoho CRM integrations.

## Overview

This project combines:

- A FastAPI API that streams chat responses using SSE
- A conversational agent with system-prompt-based intent routing
- Tool calling for CRM and vehicle lookup flows
- A Zoho OAuth client with automatic access-token refresh
- A React frontend for real-time conversational UI
- Demo data seeding for sales and service scenarios

The application is designed around a customer journey that can progress through four stages:

1. New Lead
2. Pipeline / follow-up
3. Booked / booking status
4. Service support

## Architecture at a glance

- Frontend: React + Vite in /frontend
- Backend: FastAPI in /backend
- AI runtime: Groq-compatible OpenAI client
- CRM integration: Zoho CRM via OAuth + HTTP API
- Session state: in-memory session store per chat session
- Tool layer: structured handlers for vehicle, lead, deal, and service operations

## Repository structure

- /backend/app/agent
  - system prompt and streaming agent loop
- /backend/app/routes
  - /api/chat and session endpoints
- /backend/app/tools
  - schema validation, OpenAI tool definitions, CRM handlers
- /backend/app/zoho
  - OAuth client and CRM helpers
- /backend/scripts
  - seed.py and get_refresh_token.py
- /frontend/src
  - chat UI and React components
- /.env.example
  - template for required environment variables

## Prerequisites

- Python 3.11
- Node.js 20+
- npm
- A Groq API key
- A Zoho Developer account with a self client configured

For cloud deployment (for example Render), use Python 3.11 for the backend service. This repository includes `backend/runtime.txt` to pin the deploy runtime.

## Environment setup

From the project root:

```bash
cp .env.example backend/.env
```

Then populate the values in backend/.env:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

ZOHO_CLIENT_ID=your_zoho_client_id
ZOHO_CLIENT_SECRET=your_zoho_client_secret
ZOHO_REFRESH_TOKEN=your_zoho_refresh_token
ZOHO_ACCOUNTS_URL=https://accounts.zoho.in
ZOHO_API_URL=https://www.zohoapis.in

SERVICE_MODULE_API_NAME=Cases
ASSISTANT_NAME=Automotive AI Assistant
```

## Zoho setup

### 1. Create a self client

In Zoho Developer Console:

- Create or open a project
- Create a Self Client
- Copy the Client ID and Client Secret
- Keep the values in backend/.env

### 2. Required scopes

Grant the self client the minimum scopes needed for CRM access, typically:

- ZohoCRM.modules.READ
- ZohoCRM.modules.CREATE
- ZohoCRM.modules.UPDATE
- ZohoCRM.settings.READ
- ZohoCRM.users.READ

Depending on your Zoho setup, you may also need the standard CRM access scope set for the account and data center in use.

### 3. Custom fields and CRM modules

The assistant expects the following CRM data patterns to work cleanly:

- Leads: First_Name, Last_Name, Phone, Email, City, Vehicle_Model, Lead_Source
- Contacts: Full_Name, Mobile, Phone, Email
- Deals: Deal_Name, Contact_Name, Stage, Description, Booking_ID, Vehicle_Model, Allocation_Stage, VIN, Balance_Payment_Link
- Service module: Cases or your equivalent configured module in SERVICE_MODULE_API_NAME

### 4. Data-center note

Zoho data centers differ by region. The app uses:

- India: https://accounts.zoho.in and https://www.zohoapis.in

If your account is on a different region, update ZOHO_ACCOUNTS_URL and ZOHO_API_URL to the matching endpoints or you will see authentication and API errors.

### 5. Get a refresh token

Use the helper script after creating the self client and generating a grant code from the Zoho OAuth flow:

```bash
cd backend
python scripts/get_refresh_token.py <grant_code>
```

The script prints a refresh token you should save as ZOHO_REFRESH_TOKEN in backend/.env.

## Backend setup and run

From /backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The FastAPI app starts on:

- http://localhost:8000
- API health check: http://localhost:8000/api/health
- SSE chat endpoint: http://localhost:8000/api/chat

## Frontend setup and run

From /frontend:

```bash
npm install
npm run dev
```

This will start the React app on the Vite dev server, usually:

- http://localhost:5173

The frontend dev server is configured to proxy /api requests to the FastAPI backend.

## Seed demo data

To create standard demo records for the assistant flows, run:

```bash
cd backend
source .venv/bin/activate
python scripts/seed.py
```

This creates example data for:

- a sample lead
- a contact + deal for a test drive
- a booking deal for a booked customer
- service-ready scenarios for customer support flows

## Sample conversations by stage

### 1. New Lead

```text
User: I want to know about the XUV700.
Assistant: The XUV700 is a premium SUV with a spacious cabin, strong road presence, and advanced safety features. I can help compare variants and plan a test drive.
User: I am interested in a test drive.
Assistant: Great. What is your full name?
```

### 2. Pipeline / follow-up

```text
User: My phone number is 9876543210.
Assistant: I’ve checked the record for this customer. The current stage is follow-up and the latest status is awaiting confirmation. Would you prefer a call, WhatsApp, or SMS for the next follow-up?
User: WhatsApp in the evening.
Assistant: Perfect. I’ve noted your preference for a WhatsApp follow-up in the evening.
```

### 3. Booked

```text
User: I want to know the status of booking MAH-9921.
Assistant: I’ve checked the booking. The current stage is dispatch pending, and the allocation is in progress. I can help with the next steps.
```

### 4. Service

```text
User: I need service for my car.
Assistant: Sure. Please share the registration number in the format MH12AB1234.
User: MH12AB1234
Assistant: Thank you. Please share the odometer reading in km.
```

## Troubleshooting

### INVALID_TOKEN

Symptoms:

- Zoho requests return 401
- API calls fail with INVALID_TOKEN or expired access token

Fix:

- Check that ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN are correct
- Ensure your refresh token was generated for the same Zoho account and data center
- Restart the backend to trigger a fresh token refresh
- Recheck the OAuth self client configuration and scopes

### Wrong data center

Symptoms:

- token exchange works but API requests fail
- Zoho requests time out or return access errors
- account data not found even though credentials seem valid

Fix:

- Update ZOHO_ACCOUNTS_URL and ZOHO_API_URL to the correct region
- Confirm your Zoho account is on the same region as your self client
- For India, use the Indian endpoints shown in the env example

### MANDATORY_NOT_FOUND

Symptoms:

- Zoho CRM rejects record creation because a required field is missing
- create_record calls fail with a mandatory-field validation warning

Fix:

- Make sure required CRM fields exist in the target module
- Confirm custom fields like Booking_ID, Vehicle_Model, Allocation_Stage, or Contact_Name are present in Zoho CRM
- Check field APIs names exactly; Zoho is strict about custom field names
- Use the Zoho UI to confirm field names before re-running the seed script or tool flow

## Useful notes

- The backend validates required environment variables on startup.
- The agent intentionally uses a concise prompt-driven flow to keep customer conversations natural and safe.
- The session store keeps chat state in memory for each session and is attached to the agent runtime for tool-call context.
- The frontend uses SSE to stream assistant messages and tool events in real time.

## Next steps

- Add more automated tests for edge-case CRM behavior
- Extend the tool layer with dealer search and more service workflows
- Harden production readiness for deployment, logging, and secret management
