# HR Policy Agent — One-Page Architecture Notes

## Goal
Build an HR policy assistant that answers employee questions using company policy documents instead of relying on a general model to guess rules. The system should be safe, explainable, and extendable.

## High-level architecture
The project is intentionally split into layers:

- Frontend: React UI for the chat experience
- Backend: Python + FastAPI API for requests and orchestration
- Retrieval layer: search the policy corpus for relevant passages
- Answer layer: build a grounded response from retrieved policy text
- Tools / orchestration: LangGraph + MCP for workflow decisions and actions
- Corpus: source-of-truth HR policy documents

## Request flow
1. User types a question in the UI.
2. React sends the message to the FastAPI backend.
3. The backend passes the query to the retrieval layer.
4. Retrieval searches the policy corpus for the most relevant sections.
5. The answer layer uses those passages to build a concise, grounded response.
6. The API returns the answer, citations, and trace data.
7. The UI renders the answer and lets the user inspect the citations and workflow trace.

## Why this architecture matters
This is not a generic chatbot. It is a grounded policy assistant.

- The policy corpus is the source of truth.
- Retrieval keeps the answer tied to actual policy text.
- Citations make the response explainable.
- The backend owns the logic; the frontend just presents it.
- Later, orchestration and tools allow the system to decide when to answer, ask for clarification, or trigger a structured action.

## Core responsibilities by layer
### Corpus
Stores the internal HR policies and rules. This is the system’s factual base.

### Ingestion
Reads policy files, normalizes them, and prepares them for search.

### Retrieval
Finds the policy sections most relevant to the user’s question.

### Answering
Synthesizes a short response from retrieved policy passages and returns citations.

### API
Exposes the backend to the UI and other clients.

### Orchestration (LangGraph)
Decides when the system should answer directly, ask a clarifying question, or call a tool.

### Tools (MCP)
Provides structured access to actions or policy checks without mixing everything into the chatbot prompt.

### UI (React)
Displays chat, citations, and trace information.

## Technology fit
- Python: backend logic, retrieval, orchestration, API services
- FastAPI: request/response API layer
- Pydantic: typed validation and config
- React: presentation layer for the user experience
- LangGraph: workflow and decision-making for agent behavior
- MCP: a standard way to expose reusable tools and actions

## What to explain to a team
This project demonstrates a common AI architecture pattern:

- source documents are stored in a corpus
- relevant knowledge is retrieved at runtime
- the model answers from that evidence instead of guesses
- the system can layer workflow logic and tools on top of the retrieval system
- the frontend is separate from the business logic, making the app easier to maintain and extend

## If requirements change
- Change the UI: modify the React layer
- Change the API contract: modify the FastAPI endpoints
- Change retrieval behavior: update the retrieval module
- Change answer logic: update the answer-builder layer
- Change workflow behavior: update orchestration logic
- Add new actions: add MCP tools or tool adapters

## Story in one sentence
This project is a grounded HR policy assistant built with a Python backend, a policy corpus, retrieval-based grounding, and a React frontend, with orchestration and tools added later to make the workflow safer and more capable.
