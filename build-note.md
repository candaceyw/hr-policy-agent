# Build Note

This file is a private working note for learning and presentation prep. It is intentionally separate from the project documentation and should not be treated as repo documentation for GitHub upload.

## Goal
Build the HR policy agent in a way that is understandable and teachable, while still matching the actual project architecture: Python backend, retrieval layer, LangGraph orchestration, MCP tools, and a React frontend.

## Current state
We have completed the first backend foundation:
- a policy corpus under `corpus/`
- an ingestion builder under `src/hr_agent/ingest/builder.py`
- a FastAPI app under `src/hr_agent/web/app.py`
- focused tests validating the ingestion builder and the /health + /chat endpoints

This means the app now has a simple backend that can load text files and return a grounded answer for basic queries.

## Why this matters
This is the beginning of the full stack:
- the corpus gives us the company policy knowledge base
- the ingestion step makes that knowledge searchable
- the backend turns a user question into a response using the corpus
- later, the agent layer adds routing, tool use, and tool traces
- the UI layer renders the final result to the user

## What we are learning here
### 1. Corpus-first design
The policy documents are the source of truth. The system should not rely on the model to invent policy knowledge. The agent should answer from documents and cite them.

This is important for a presentation because it shows the difference between:
- a general chatbot that guesses
- a grounded HR assistant that uses policy documents and cites sources

### 2. Backend-first architecture
The Python backend is where the real logic starts. It is responsible for:
- app setup
- API routes
- request handling
- retrieval logic
- orchestration
- domain-specific workflow decisions

The frontend is not the brain of the system; it is the interface.

### 3. Retrieval layer is the bridge between docs and answers
A large language model alone is not enough for a reliable policy assistant. We need to retrieve the most relevant policy sections and then synthesize the answer using that context.

In the next step, we should add:
- a query matcher or vector search
- section-level retrieval
- citation formatting
- answer grounding based on retrieved chunks

### 4. LangGraph adds decision-making
After the retrieval layer, we add a graph.

This graph decides:
- Is this a policy question?
- Is the question ambiguous?
- Is the request out of scope?
- Does the user need a tool call?
- Should the system ask for clarification?
- Should the system escalate or refuse?

LangGraph helps model that control flow clearly.

### 5. MCP standardizes tools
MCP gives us a consistent tool interface. Instead of direct custom function calls, the agent discovers tools and calls them over a standard protocol.

This matters because it makes the system modular and closer to real-world AI agent patterns.

### 6. React is just the presentation layer
The frontend should not contain the actual policy logic. It should simply:
- allow the user to type a message
- show assistant responses
- render citations
- show tool trace details
- allow confirm/deny for mock actions

This separation keeps the app maintainable and easier to explain.

## Architecture progression
We are intentionally building in this order:
1. corpus
2. ingestion
3. FastAPI basic app
4. retrieval and grounding
5. LangGraph orchestration
6. MCP tool layer
7. React frontend UI

This order helps learning and reduces confusion.

## Presentation talking points
A strong presentation can explain the project like this:

- The system is an HR policy assistant that answers grounded questions using internal documents.
- It is built as a full-stack AI app with a Python backend and a React frontend.
- The backend loads a synthetic corpus of HR policies and uses retrieval to ground answers.
- Later, the agent layer decides if the question requires additional tools or clarification.
- Tools are exposed via MCP so the agent can access policy checks, employee records, and mock workflow actions.
- The React UI renders answers, citations, and trace information in a simple chat interface.

## What to explain in the next walkthrough
We should next walk through:
- how the corpus is structured
- how ingestion turns markdown into searchable content
- how a user query is matched to policy text
- how citations are generated
- how the next layer adds tool discipline and orchestration

## Important principle
For this project and this presentation, the best story is not "we built a generic chatbot." The best story is:

"We built a grounded HR policy assistant that uses a curated corpus, structured tools, and an agentic workflow to answer employee questions safely and cite policy sources."

## Next implementation focus
The immediate next step should be retrieval and citation logic.

That will likely involve:
- building a simple search function against the corpus
- chunking or splitting content into passages
- ranking relevant passages by similarity
- returning those passages to the API response
- attaching them as citations for the answer

Once retrieval works, the next step is LangGraph.

## Current milestone: grounded retrieval is live
We have now implemented the first retrieval-based grounding step in the backend.

This matters because it demonstrates the key architecture change from a static prompt response to a source-grounded answer:
- the user asks a policy question
- the system searches the corpus for relevant passages
- the top matches are ranked and returned with section context
- those passages become citations for the final answer
- the answer is therefore tied to concrete policy text rather than invented content

This is the clearest teaching moment for the project because it shows the difference between:
- a generic LLM response
- a grounded HR assistant using policy documents as the source of truth

When we explain this in the presentation, we can say:
'The retrieval layer is the bridge between the corpus and the answer. It turns the model from a general answer generator into a policy-aware assistant with traceable citations.'

## Notes for future slides
Potential slide sections:
- Problem and project goal
- Architecture overview
- Policy corpus and mock data
- Retrieval and grounding
- Agent orchestration with LangGraph
- MCP tools and workflows
- React UI and end-user experience
- Testing and evaluation

## Reminder
This file is private and is not for the GitHub repo. It is for learning while building and for presentation notes.
