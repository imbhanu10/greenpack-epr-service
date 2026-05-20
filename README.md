# GreenPack EPR Service

GreenPack EPR Service is a lightweight FastAPI backend for Extended Producer Responsibility (EPR) compliance workflows. It validates monthly producer declarations, persists them in SQLite, reconciles declared packaging quantities against ERP procurement data, and uses Gemini only for narrative summaries and document-grounded RAG answers.

The project is intentionally small, production-oriented, and demo-ready. Deterministic compliance calculations stay in Python services, while Gemini is used only where natural language generation adds value.

## Highlights

- FastAPI backend with thin route handlers
- Pydantic v2 request and response validation
- SQLite persistence through SQLAlchemy
- Deterministic declaration-vs-procurement reconciliation
- Mismatch detection for variances greater than 5%
- Gemini 2.5 Flash-Lite summary generation
- Lightweight RAG over local compliance documents
- ChromaDB vector search with sentence-transformers embeddings
- Anti-hallucination fallback for unsupported RAG questions
- Startup-safe lazy loading for AI and vector-store dependencies
- Pytest coverage for validation, submission, reconciliation, startup, and RAG fallback

## Architecture

```text
greenpack_epr_service/
|-- app/
|   |-- main.py                 # FastAPI app factory and startup initialization
|   |-- api/
|   |   `-- routes.py           # Thin HTTP route handlers
|   |-- core/
|   |   `-- config.py           # Pydantic settings and environment config
|   |-- db/
|   |   |-- database.py         # SQLite engine, sessions, table initialization
|   |   `-- crud.py             # SQLAlchemy persistence operations
|   |-- schemas/
|   |   `-- declaration.py      # Pydantic v2 request/response schemas
|   |-- services/
|   |   |-- reconciliation_service.py  # Deterministic reconciliation logic
|   |   |-- llm_service.py             # Gemini summary generation
|   |   `-- rag_service.py             # RAG retrieval and answer generation
|   |-- prompts/
|   |   `-- summary_prompt.txt  # External prompt for summary generation
|   `-- utils/
|       `-- helpers.py          # Reusable pure helper functions
|-- data/
|   |-- mock_erp_feed.csv       # Mock ERP procurement data
|   `-- documents/              # Local RAG corpus
|-- tests/                      # Pytest suite
|-- requirements.txt
|-- .env.example
`-- run.py
```

The core design rule is separation of concerns:

- Routes translate HTTP requests and responses.
- Schemas validate API input and output.
- Services contain business logic and AI integration.
- The database layer owns persistence.
- Prompts live outside Python code.

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/submit` | Validate and store a producer declaration |
| `GET` | `/summary/{producer_id}/{month}` | Return reconciliation results plus Gemini summary |
| `POST` | `/ask` | Answer compliance questions using local-document RAG |

Interactive API docs are available after startup:

```text
http://127.0.0.1:8000/docs
```

## Setup

### 1. Create a virtual environment

Python 3.11+ is recommended.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a local `.env` file from `.env.example`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

Do not commit `.env`. The repository includes `.env.example` for safe configuration reference.

### 4. Run the API

```bash
uvicorn app.main:app --reload
```

The API runs at:

```text
http://127.0.0.1:8000
```

## Example Requests

### Submit a declaration

```bash
curl -X POST http://127.0.0.1:8000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "producer_id": "GREENPACK-001",
    "month": "2026-04",
    "declared_quantities_kg": {
      "rigid_plastic": 12000,
      "flexible_plastic": 8500,
      "multilayer_plastic": 3200
    }
  }'
```

Behavior:

- validates `YYYY-MM` month format
- rejects negative and non-finite quantities
- rejects extra fields
- generates a UUID `record_id`
- adds a UTC `created_at` timestamp
- persists the declaration in SQLite

### Get reconciliation summary

```bash
curl http://127.0.0.1:8000/summary/GREENPACK-001/2026-04
```

Response shape:

```json
{
  "producer_id": "GREENPACK-001",
  "month": "2026-04",
  "reconciliation_results": [
    {
      "material_type": "flexible_plastic",
      "declared_quantity_kg": 8500.0,
      "procured_quantity_kg": 8000.0,
      "variance_kg": 500.0,
      "variance_percent": 6.25,
      "is_mismatch": true
    }
  ],
  "llm_summary": "..."
}
```

### Ask a compliance question

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What should producers do when EPR quantities do not match procurement records?"
  }'
```

Response shape:

```json
{
  "answer": "...",
  "citations": [
    "cpcb_guidelines.txt"
  ]
}
```

If the local documents do not support an answer, the service returns:

```text
I do not know based on the provided documents
```

## Deterministic Reconciliation

Reconciliation is handled in `app/services/reconciliation_service.py`.

The service:

- loads procurement records from `data/mock_erp_feed.csv`
- filters records by `producer_id` and `month`
- aggregates procured quantities by material type
- compares procured totals against submitted declared quantities
- calculates variance in kilograms
- calculates variance percentage against procured quantity
- flags mismatches when variance is greater than 5%

Gemini does not perform calculations, verify numbers, or decide mismatch status. It receives structured reconciliation JSON and writes a concise human-readable summary.

## Gemini Integration

Gemini 2.5 Flash-Lite is used for two focused tasks:

1. Generate a 3-5 sentence reconciliation summary from deterministic JSON.
2. Generate document-grounded answers for `/ask` using retrieved RAG context.

The summary prompt is stored separately in:

```text
app/prompts/summary_prompt.txt
```

This keeps prompt changes separate from application logic and reinforces that the model is a narrative layer, not a calculation engine.

## RAG Pipeline

The RAG flow is implemented in `app/services/rag_service.py`.

It uses:

- local `.txt` documents from `data/documents/`
- `RecursiveCharacterTextSplitter` from `langchain-text-splitters`
- `sentence-transformers` for local embeddings
- ChromaDB for lightweight vector retrieval
- Gemini for grounded answer generation

RAG stability improvements include:

- lazy loading for Gemini, ChromaDB, and the embedding model
- project-root-relative document paths
- safe handling for empty collections and empty retrievals
- graceful fallback when Gemini answer generation fails
- citations returned from retrieved document metadata

The first `/ask` request may take longer because the embedding model is loaded lazily to keep FastAPI startup reliable.

## Database and Startup Behavior

SQLite is used for local persistence to keep the service simple and self-contained.

Startup behavior:

- `initialize_database()` runs during FastAPI app creation
- tables are available before any request is handled
- declaration writes still preserve existing CRUD behavior

This avoids a fresh-database edge case where a read endpoint could run before tables existed.

## Technology Choices

| Area | Choice | Why |
| --- | --- | --- |
| API | FastAPI | Typed, lightweight, and well suited for backend APIs |
| Validation | Pydantic v2 | Strict request validation and clean response models |
| Persistence | SQLite + SQLAlchemy | Simple local database without extra infrastructure |
| LLM | Gemini 2.5 Flash-Lite | Fast, cost-aware summaries and grounded answers |
| Embeddings | sentence-transformers | Local semantic embeddings for demo-friendly RAG |
| Vector store | ChromaDB | Lightweight local vector search |
| Text splitting | langchain-text-splitters | Stable recursive chunking utility |
| Testing | pytest | Fast route and service verification |

## Testing

Run the test suite:

```bash
python -m pytest
```

Current coverage includes:

- invalid declaration payload rejection
- negative quantity validation
- successful declaration submission
- deterministic reconciliation mismatch detection
- Gemini summary integration through mocking
- RAG unknown-answer fallback
- production-style FastAPI startup import

External model behavior is mocked where appropriate so tests remain fast and deterministic.

## Production-Readiness Notes

Completed stability work:

- fixed LangChain text splitter compatibility by using `langchain-text-splitters`
- removed import-time initialization of Gemini, ChromaDB, and sentence-transformers
- added lazy AI/vector-store initialization
- fixed document path resolution to avoid current-working-directory bugs
- hardened empty ChromaDB retrieval handling
- added Gemini failure fallback for RAG answers
- updated Pydantic settings to v2 configuration style
- added explicit `/summary` response model
- initialized SQLite tables during app startup
- added startup import coverage in tests

Known demo tradeoffs:

- SQLite is appropriate for a local screening project; PostgreSQL would be better for multi-user production.
- ChromaDB is used as a lightweight local vector store; persistent production indexing would need additional setup.
- Authentication and producer-level authorization are intentionally out of scope for this assignment.

## AI-Assisted Development Workflow

This project was built iteratively with AI assistance for scaffolding, validation logic, service design, test planning, and review. Human engineering judgment shaped the final architecture: deterministic logic remains separate from generative AI, route handlers stay thin, and the implementation avoids unnecessary infrastructure such as agents, queues, Redis, Celery, Kafka, or LangGraph.

The result is a maintainable backend that demonstrates practical AI integration without handing business-critical calculations to an LLM.

## Future Improvements

- Add authentication and producer-level authorization
- Migrate SQLite to PostgreSQL for multi-user deployments
- Add Alembic migrations
- Support uploaded ERP files instead of a static CSV
- Add PDF ingestion for the RAG corpus
- Persist ChromaDB indexes to disk
- Add structured logging and request IDs
- Add Docker packaging for deployment

##Engineering Notes
Stack Choices

This project uses:

FastAPI for the backend API because of its strong typing, async support, and clean developer experience.
Pydantic v2 for strict request/response validation.
SQLAlchemy with SQLite for lightweight local persistence.
ChromaDB and sentence-transformers for local RAG retrieval.
Google Gemini 2.5 Flash-Lite for concise narrative summaries and grounded document QA.

The stack was intentionally chosen to keep the service lightweight, locally runnable, and easy to evaluate without requiring external infrastructure.

AI-Assisted Development Disclosure

AI coding assistants were used during development for scaffolding, refactoring suggestions, debugging, test planning, and documentation support. Final implementation decisions, architecture, reconciliation logic, validation behavior, and production trade-offs were reviewed and controlled manually.

LLMs are intentionally limited to narrative and retrieval tasks only. All compliance calculations and reconciliation logic remain deterministic Python code.

Trade-Off Made

A deliberate trade-off was choosing Gemini API integration instead of running a local LLM through Ollama or self-hosted inference. This reduced setup complexity, improved iteration speed, and kept the project lightweight for evaluation, at the cost of depending on an external API service.

## Submission Summary

GreenPack EPR Service demonstrates a balanced backend approach for an AI-integrated compliance workflow:

- deterministic reconciliation for correctness
- Gemini for concise narrative generation
- lightweight RAG for document-grounded compliance support
- FastAPI and Pydantic for clean API boundaries
- SQLite and ChromaDB for simple local demo infrastructure
- tests and startup checks for submission reliability
