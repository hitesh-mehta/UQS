# 🧠 Universal Query Solver (UQS)
### AI-Driven Data Warehouse & Business Intelligence Platform
> **Hackathon Submission — NatWest Group: Talk to Data: Seamless Self-Service Intelligence**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-4CAF50?logo=python)](https://github.com/langchain-ai/langgraph)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue)](LICENSE)

---

## 📋 Table of Contents

1. [What is UQS?](#-what-is-uqs)
2. [The Three Pillars](#-the-three-pillars)
3. [Why LangGraph?](#-why-langgraph)
4. [System Architecture](#-system-architecture)
5. [Core Engines](#-core-engines)
6. [Security & Robustness](#-security--robustness)
7. [File Structure](#-file-structure)
8. [Prerequisites](#-prerequisites)
9. [Installation & Setup](#-installation--setup)
10. [Environment Variables](#-environment-variables)
11. [Running the Project](#-running-the-project)
12. [API Reference](#-api-reference)
13. [RBAC & Onboarding Guide](#-rbac--onboarding-guide)
14. [Development Status](#-development-status)
15. [Technology Stack](#-technology-stack)
16. [Contributing & DCO](#-contributing--dco)
17. [Presentation](#-presentation)
---

## 🚀 What is UQS?

**Universal Query Solver (UQS)** is an AI-native Business Intelligence platform that lets any user — technical or non-technical — ask questions about enterprise data in plain English and receive instant, accurate, cited answers.

It eliminates the need for SQL knowledge, data science expertise, or navigating complex BI dashboards. Behind a single conversational interface, UQS orchestrates **five specialized AI engines** through a **LangGraph state machine**, enforces database-level Role-Based Access Control (RBAC), streams responses token-by-token, and intelligently caches reports to serve the majority of queries near-instantly.

### Key Differentiators

| Feature | Description |
|---|---|
| 🗣️ **Single NL Interface** | One chat box for SQL queries, analytics, predictions, and document Q&A |
| 🔀 **LangGraph Orchestration** | Stateful pipeline graph — visual, resumable, fault-tolerant with per-node timeouts |
| 🔐 **DB-Level RBAC** | Roles map to read-only PostgreSQL views — LLM never sees unauthorized data |
| ⚡ **Cache Intelligence** | Pre-generated hourly/daily/weekly/monthly reports served in milliseconds |
| 🤖 **5 Specialized Engines** | SQL, Analytical, Predictive, RAG, RAG++ — each optimal for its query type |
| 📊 **Explainable AI** | Every answer cites source tables, documents, confidence, and reasoning |
| 🔄 **Continual Learning** | ML models retrain daily; versioned with admin rollback up to 5 versions |
| 📡 **SSE Streaming** | Token-by-token streaming responses with automatic fallback to JSON |
| 🛡️ **Attack Resistance** | Rate limiting (30/min), prompt injection detection, SQL safety blocklist |

---

## 🎯 The Three Pillars

### ✅ Clarity
- LLM-generated plain-English answers — no SQL or jargon exposed to users
- Every response includes a narrative description + visual (table/chart/predictions)
- Consistent metric definitions enforced via schema and prompt engineering
- Streaming token delivery so users see answers forming in real time

### ✅ Trust
- Every response cites the exact source table, view, or document used
- RBAC ensures users only ever see data within their authorization scope
- All queries and LLM calls are logged for full audit trails
- SQL injection prevention via parameterized queries + LLM output validation + expanded blocklist
- Prompt injection detection heuristics sanitize every input before it reaches the LLM

### ✅ Speed
- Cache Intelligence Layer serves repeated queries in near real-time (~milliseconds)
- Lightweight local LLM (Gemma 2B via Ollama) minimizes inference latency
- Parallel SQL sub-queries in the Analytical Engine reduce wait times
- LangGraph's conditional edges short-circuit the pipeline on cache hits — no engine invoked at all

---

## 🔀 Why LangGraph?

Traditional BI pipelines use flat `if/elif` routing that is:
- Hard to visualize and debug
- Brittle on failure — one error kills the entire request
- Impossible to resume, inspect, or trace node-by-node

**LangGraph** transforms the UQS orchestration into a **typed StateGraph** where:

```
UQSState (TypedDict) flows through nodes:

START
  ↓
[classify]  ────── irrelevant/error ──────────────────→ [format_response]
  ↓ relevant
[check_cache] ──── cache hit ────────────────────────→ [format_response]
  ↓ cache miss
  ├── query_type=sql          → [sql_engine]          → [format_response]
  ├── query_type=analytical   → [analytical_engine]   → [format_response]
  ├── query_type=predictive   → [predictive_engine]   → [format_response]
  ├── query_type=rag          → [rag_engine]           → [format_response]
  └── query_type=rag++        → [rag_plus_plus]       → [format_response]
                                                              ↓
                                                             END
```

Every node:
- Receives the full `UQSState` and returns only the keys it changes (LangGraph merges)
- Has a **28-second `asyncio.wait_for` timeout guard** — no node can hang forever
- Returns structured error info into `state["error"]` for graceful degradation
- Logs its execution to the structured audit trail

The cache check has a **5-second timeout** — it fails open (cache miss) so a slow cache never blocks the user.

---

## 🏗️ System Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │           USER INTERFACE LAYER               │
                    │  Next.js 16 — Dark-mode Chat UI              │
                    │  • Token-streaming SSE display               │
                    │  • ResponseCard + ChartRenderer              │
                    │  • Cache/Model/Engine/RBAC admin tabs        │
                    └──────────────────┬───────────────────────────┘
                                       │ SSE stream / JSON
                    ┌──────────────────▼───────────────────────────┐
                    │            FASTAPI GATEWAY LAYER             │
                    │  • JWT Auth → Role extraction                │
                    │  • Rate Limiter (SlowAPI: 30 req/min/IP)     │
                    │  • Input Sanitizer (injection, length, null) │
                    │  • TrustedHost + CORS Middleware             │
                    │  • Structured 429/500 error responses        │
                    └──────────┬───────────────────────────────────┘
                               │
               ┌───────────────▼────────────────────┐
               │        RBAC / Context Layer         │
               │  role → DB views → schema string   │
               │  injected into LLM system prompt   │
               │  (LLM never sees other roles' data)│
               └───────────────┬────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      LANGGRAPH STATE MACHINE                            │
│                                                                         │
│  UQSState: { query, session_id, session, classification,               │
│              cache_result, engine_result, final_response, error }       │
│                                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────────────────┐  │
│  │  classify   │──▶│ check_cache  │──▶│  Engine Nodes (parallel-safe)│  │
│  │  (LLM call) │   │  (5s timeout)│   │   sql / analytical          │  │
│  └─────────────┘   └──────────────┘   │   predictive / rag / rag++  │  │
│                                        └─────────────────────────────┘  │
│                                                      │                  │
│                                          ┌───────────▼──────────────┐   │
│                                          │    format_response       │   │
│                                          │ (assemble QueryResponse) │   │
│                                          └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                               │
               ┌───────────────▼────────────────────┐
               │          DATA LAYER                 │
               │  Supabase PostgreSQL (RBAC views)   │
               │  FAISS Vector Store (RAG chunks)    │
               │  Model Registry (XGBoost/RF/Prophet)│
               │  FIFO Report Cache (JSON files)     │
               └────────────────────────────────────┘
```

### End-to-End Data Flow

```
User natural-language query
    │
    ├─ 1. Auth & RBAC         → JWT validated → role extracted → schema loaded
    ├─ 2. Rate Limit           → 30 req/min per IP enforced
    ├─ 3. Input Sanitization   → injection patterns, null bytes, 1000-char cap
    ├─ 4. LangGraph: classify  → LLM: relevant? what engine type?
    │       ├─ irrelevant → polite rejection response
    │       └─ relevant  → continue
    ├─ 5. LangGraph: cache     → LLM checks cached summaries semantically
    │       ├─ HIT   → return cached answer in < 100ms
    │       └─ MISS  → route to appropriate engine
    ├─ 6. Engine Execution     → SQL / Analytical / Predictive / RAG / RAG++
    ├─ 7. Response Format      → assemble narrative + metrics + chart + sources
    └─ 8. SSE Stream / JSON    → word-by-word streaming OR full JSON fallback
```

---

## ⚙️ Core Engines

### 1. 🔍 SQL Engine

Converts natural language to SQL using SOTA **DIN-SQL / DAIL-SQL** patterns:

- **Schema Injection** — only the user's role-scoped views are in the LLM context
- **Schema Linking** — LLM explicitly identifies relevant tables/columns before writing SQL
- **Self-Correction Loop** — on SQL execution error, the error is fed back to LLM for one retry
- **Safety Validation** — 25+ blocked keywords: `DELETE`, `UPDATE`, `INSERT`, `DROP`, `EXEC`, `COPY`, `GRANT`, `REVOKE`, and more
- **Result Explanation** — raw rows always accompanied by plain-English narrative

```
NL Query
  → [Schema Linking: identify views + columns]
  → [LLM: generate SELECT-only SQL]
  → [Safety Check: blocklist validation]
  → [Execute against Supabase]
  → on error: [feed error to LLM → corrected SQL → re-execute]
  → [LLM: explain results in plain English]
```

### 2. 📈 Analytical Engine

Sits on top of the SQL Engine to answer complex, insight-oriented questions:

| Sub-type | Example Query |
|---|---|
| `trend_analysis` | "How has revenue trended over 6 months?" |
| `causal_diagnostic` | "Why did churn increase in March?" |
| `comparative` | "How does Region A compare to Region B?" |
| `what_if` | "What if we reduce ad spend by 20%?" |
| `time_series` | "Show the weekly pattern in support tickets" |
| `decomposition` | "Break down total costs by department" |

The LLM acts as an **Algorithm Brain** — it:
1. Deconstructs the complex query into sub-questions
2. Selects the appropriate statistical method (correlation, decomposition, trend slope, etc.)
3. Orchestrates multiple parallel SQL sub-queries
4. Receives all results and synthesizes them into a coherent narrative with supporting charts

### 3. 🔮 Predictive Engine

Zero-expertise ML forecasting, clustering, and anomaly detection:

- **Multi-Model Training Pool** — XGBoost, RandomForest, LightGBM, Prophet (time-series), IsolationForest (anomaly)
- **Automated Model Selection** — best model by RMSE (regression), F1 (classification), MAE (forecasting), Silhouette (clustering)
- **Hyperparameter Tuning** — Grid/Random/Bayesian search
- **Model Registry** — versioned storage (`v1`, `v2`, ...) with active pointer
- **Continual Learning** — daily cron retraining; auto-promotes only if new model outperforms current
- **Admin Rollback** — up to 5 version lookback, with audit log

```
models/
├── target_revenue/
│   ├── v1/   (model.pkl + metadata.json + dataset_hash)
│   ├── v2/   (improved model after retraining)
│   └── active → v2            # pointer to best version
└── target_churn/
    └── v1/
```

### 4. 📄 RAG Engine

Ground answers in user-uploaded documents (PDF, DOCX, TXT):

```
Upload:   Document → chunking (512 tokens, 64 overlap)
                   → Embeddings (all-MiniLM-L6-v2, 384-dim)
                   → FAISS index

Query:    User query → embed → Top-K similarity search
                     → retrieved chunks → LLM Answer
                     → Sources cited with filename + page
```

### 5. 🔗 RAG++ Engine

Hybrid answers combining live DB data **and** uploaded documents:

```
User Query
    ├── SQL Engine      → fetch live DB context relevant to the query
    └── RAG Engine      → retrieve document chunks
              ↓
    Context Merged → LLM synthesizes unified answer
              ↓
    Response cites both DB tables and document pages/sources
```

This enables questions like: *"Does the Q3 report match our actual sales numbers?"* — answered by comparing the uploaded PDF against live database figures.

---

## 🛡️ Security & Robustness

| Layer | Mechanism | Detail |
|---|---|---|
| **Authentication** | JWT (HS256) | Role embedded in token claims |
| **Authorization** | DB-view RBAC | LLM physically cannot access unauthorized schema |
| **Rate Limiting** | SlowAPI (30/min per IP) | Returns structured `429` with `retry_after` |
| **Input Sanitization** | Regex + length cap | Prompt injection patterns, null bytes, max 1000 chars |
| **SQL Safety** | 25+ keyword blocklist | DML/DDL/system commands all blocked |
| **Timeout Guards** | `asyncio.wait_for` | 28s per engine node, 5s for cache check |
| **Error Handling** | Global FastAPI handler | All exceptions → structured `{"error": "...", "code": "..."}` JSON |
| **Audit Logging** | Structured JSON logs | Every query, classification, and engine response logged |

### Prompt Injection Defense

Every query is checked against heuristics before reaching the LLM:

```python
# Blocked patterns (case-insensitive)
"ignore previous", "disregard all", "you are now",
"act as", "system:", "jailbreak", "pretend you",
"forget your instructions", "override the rules"
```

---

## 📁 File Structure

```
UQS/
├── README.md                          ← You are here
├── CONTRIBUTING.md                    ← DCO sign-off guide
├── LICENSE                            ← Apache 2.0
├── .env.example                       ← Copy to .env and fill in values
├── .gitignore
│
├── backend/                           ← FastAPI Python backend (the brain)
│   ├── main.py                        ← FastAPI app with middleware + lifespan
│   ├── config.py                      ← Pydantic settings from .env
│   ├── requirements.txt               ← All Python dependencies
│   │
│   ├── graph/                         ← LangGraph orchestration pipeline ⭐
│   │   ├── __init__.py
│   │   ├── state.py                   ← UQSState TypedDict (shared pipeline state)
│   │   ├── nodes.py                   ← All node functions (classify, cache, engines)
│   │   └── pipeline.py                ← StateGraph compilation + singleton
│   │
│   ├── core/                          ← Core infrastructure
│   │   ├── database.py                ← Supabase/PostgreSQL async connection
│   │   ├── auth.py                    ← JWT authentication & role extraction
│   │   ├── rbac.py                    ← Role → DB view mapping + schema loader
│   │   ├── logger.py                  ← Structured JSON audit trail logging
│   │   └── security.py                ← Rate limiter, input sanitizer, SQL blocklist
│   │
│   ├── engines/                       ← The 5 specialized AI engines
│   │   ├── classifier.py              ← Query Classification Engine (LLM routing)
│   │   ├── sql_engine.py              ← NL→SQL pipeline (DIN-SQL + self-correction)
│   │   ├── analytical_engine.py       ← Algorithm brain for complex insights
│   │   ├── predictive_engine.py       ← ML inference & model management
│   │   ├── rag_engine.py              ← Document Q&A via FAISS vector retrieval
│   │   └── rag_plus_plus.py           ← Hybrid DB + document context merging
│   │
│   ├── cache/                         ← Cache Intelligence Layer
│   │   ├── cache_manager.py           ← FIFO report cache (4 granularities)
│   │   ├── cache_query.py             ← LLM-assisted semantic cache hit detection
│   │   └── cron_generator.py          ← APScheduler report generation
│   │
│   ├── llm/                           ← LLM abstraction layer
│   │   ├── client.py                  ← Pluggable LLM client (Ollama/OpenAI/Anthropic)
│   │   ├── context_manager.py         ← Per-user schema + session context store
│   │   └── prompts/
│   │       └── all_prompts.py         ← All 7 system prompts (versioned, commented)
│   │
│   ├── models/                        ← ML Model Registry & Lifecycle
│   │   ├── registry.py                ← Versioned model storage & rollback
│   │   ├── trainer.py                 ← Multi-model training pool
│   │   ├── evaluator.py               ← Metrics & automated model selection
│   │   └── continual_learning.py      ← Daily cron retraining pipeline
│   │
│   ├── vector_store/                  ← RAG vector storage
│   │   ├── store.py                   ← FAISS index abstraction
│   │   └── ingestion.py               ← PDF/DOCX/TXT chunking + indexing
│   │
│   ├── schema/                        ← Schema management & onboarding
│   │   └── metric_dict.py             ← Domain terminology dictionary
│   │
│   ├── api/                           ← FastAPI route handlers
│   │   ├── query.py                   ← POST /api/query + GET /api/query/stream (SSE)
│   │   ├── documents.py               ← POST /api/documents/upload
│   │   ├── admin.py                   ← Admin: rollback, cache flush, retrain
│   │   └── schema_api.py              ← POST /api/schema — CSV onboarding
│   │
│   └── tests/
│       └── test_core.py               ← Unit tests for all core components
│
├── frontend/                          ← Next.js 16 frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── .env.local                     ← NEXT_PUBLIC_API_URL
│   │
│   ├── app/
│   │   ├── layout.tsx                 ← SEO metadata + Google Fonts
│   │   ├── page.tsx                   ← 5-tab SPA (Chat/Cache/Models/Engines/RBAC)
│   │   └── globals.css                ← Full dark design system (600+ lines)
│   │
│   ├── components/
│   │   ├── ChatInterface.tsx           ← Streaming chat UI with SSE + stop button
│   │   ├── ResponseCard.tsx            ← Metrics grid + chart embed + source refs
│   │   ├── ChartRenderer.tsx           ← Bar/Line/Pie/Table/Predictions (Recharts)
│   │   ├── SourceBadge.tsx             ← "Source: table_name" reference chips
│   │   ├── QueryTypeIndicator.tsx      ← Engine + sub-type color-coded badges
│   │   ├── DocumentUpload.tsx          ← Drag-and-drop document upload
│   │   ├── CacheStatusPanel.tsx        ← 4-granularity fill bars + summaries
│   │   └── ModelStatus.tsx             ← Version pills, metrics, feature list
│   │
│   └── lib/
│       ├── api.ts                      ← Typed API client with streamQuery() SSE
│       └── types.ts                    ← Shared TypeScript interfaces
│
├── scripts/
│   ├── init_db.py                     ← DB schema + RBAC view initialization
│   └── seed_cache.py                  ← Generate initial report cache
│
└── docs/
    ├── architecture.md                ← Mermaid diagrams + design decisions
    └── (api_reference.md, rbac_guide.md, deployment.md — planned)
```

---

## ✅ Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| Ollama | Latest | Local LLM runtime (recommended) |
| Gemma 2B via Ollama | — | `ollama pull gemma2:2b` |
| Supabase Account | — | Free tier sufficient for development |
| Git | 2.x+ | With DCO sign-off (`git commit -s`) |

### Install Ollama

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma2:2b

# Windows: download from https://ollama.com/download
# then run:
ollama pull gemma2:2b
```

---

## 🛠️ Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/hitesh-mehta/UQS
cd UQS
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — fill in SUPABASE_URL, DATABASE_URL, JWT_SECRET
```

### 3. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Install all dependencies (including LangGraph, SlowAPI, etc.)
pip install -r requirements.txt
```

### 4. Initialize the Database *(optional — creates demo schema + seed data)*

```bash
python -m scripts.init_db
```

This creates:
- Demo tables: `sales_fact`, `customers`, `products`, `regions`
- RBAC views: `analyst_sales_view`, `rm_sales_view`, `audit_trail_view`, `dashboard_summary_view`
- Sample seed data for immediate querying

### 5. Start Backend

```bash
# From project root
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Or from backend/ directory
uvicorn main:app --reload
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs` *(dev mode only)*

### 6. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

- Frontend: `http://localhost:3000`

### 7. Start Ollama (separate terminal)

```bash
ollama serve
```

### 8. Login & Start Querying

1. Open `http://localhost:3000`
2. Select a role from the dropdown: **Admin / Analyst / Regional Manager / Auditor / Viewer**
3. Click **Connect & Enter →**
4. Ask any question about your data!

---

## 🔐 Environment Variables

Copy `.env.example` to `.env`:

```bash
# ── Supabase ──────────────────────────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# ── LLM (choose one provider) ──────────────────────────────────────────
LLM_PROVIDER=ollama                  # ollama | openai | anthropic | google
LLM_MODEL=gemma2:2b                  # gemma2:2b | llama3.2 | mistral | gpt-4o
LLM_BASE_URL=http://localhost:11434  # Ollama API URL
OPENAI_API_KEY=                      # if using LLM_PROVIDER=openai
ANTHROPIC_API_KEY=                   # if using LLM_PROVIDER=anthropic

# ── Embeddings ────────────────────────────────────────────────────────
EMBEDDING_MODEL=all-MiniLM-L6-v2    # sentence-transformers model (local)

# ── Auth ──────────────────────────────────────────────────────────────
JWT_SECRET=your-very-long-random-secret-minimum-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ── Security ──────────────────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE=30             # API rate limit per IP
QUERY_MAX_LENGTH=1000                # Max chars per query
REQUEST_TIMEOUT_SECONDS=30           # Global per-request timeout

# ── Cache ─────────────────────────────────────────────────────────────
CACHE_STORE_PATH=./cache_store       # Filesystem cache directory
CACHE_RETENTION_UNITS=10             # 10 per granularity (hourly/daily/weekly/monthly)

# ── ML Model Registry ─────────────────────────────────────────────────
MODEL_REGISTRY_PATH=./model_registry
MAX_ROLLBACK_VERSIONS=5

# ── Vector Store ──────────────────────────────────────────────────────
VECTOR_STORE_TYPE=faiss              # faiss | qdrant
FAISS_INDEX_PATH=./faiss_index
QDRANT_URL=http://localhost:6333     # if using qdrant

# ── API Server ────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true                           # Set false in production (disables /docs)

# ── Scheduling ────────────────────────────────────────────────────────
CRON_ENABLED=false                   # Enable scheduled report generation
```

---

## ▶️ Running the Project

### Development Mode

**Terminal 1 — Local LLM (Ollama)**
```bash
ollama serve
```

**Terminal 2 — Backend**
```bash
cd backend
source venv/bin/activate        # or venv\Scripts\activate on Windows
uvicorn backend.main:app --reload --port 8000
```

**Terminal 3 — Frontend**
```bash
cd frontend
npm run dev
```

Then open `http://localhost:3000` and login with any role.

### Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## 📡 API Reference

### Authentication

All endpoints require a JWT token in the `Authorization: Bearer <token>` header.

**Dev token** (available when `DEBUG=true`):
```bash
curl -X POST "http://localhost:8000/dev/token?role=analyst"
# Returns: { "access_token": "eyJ...", "token_type": "bearer", "role": "analyst" }
```

### Core Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/health` | System health + pipeline info | Public |
| `POST` | `/api/query` | Submit NL query, get full JSON response | ✅ JWT |
| `GET` | `/api/query/stream` | Submit NL query, get SSE token stream | ✅ JWT |
| `POST` | `/api/documents/upload` | Upload PDF/DOCX/TXT for RAG | ✅ JWT |
| `GET` | `/api/documents/list` | List ingested document sources | ✅ JWT |
| `POST` | `/api/schema/onboard` | Onboard CSV dataset with LLM schema proposal | ✅ Admin |
| `GET` | `/api/admin/cache/status` | View cache contents + granularity stats | ✅ JWT |
| `POST` | `/api/admin/cache/flush` | Flush cache (all or by granularity) | ✅ Admin |
| `GET` | `/api/admin/models/registry` | List all ML models + versions + metrics | ✅ JWT |
| `POST` | `/api/admin/models/rollback` | Roll back a target prediction model | ✅ Admin |
| `POST` | `/api/admin/models/retrain` | Trigger immediate retraining | ✅ Admin |

### Query Request/Response

**Request:**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did sales drop in February?",
    "session_id": "user-001"
  }'
```

**Response:**
```json
{
  "answer": "Sales dropped 11.3% in February compared to January. The primary driver was a 23% decline in the North region, where the winter promo campaign ended on Jan 31. The South and East regions remained stable.",
  "engine": "analytical",
  "query_type": "causal_diagnostic",
  "sources": ["analyst_sales_view", "region_dim_view"],
  "key_metrics": [
    { "label": "Feb Revenue", "value": "$1.84M", "change": "-11.3%" },
    { "label": "North Drop", "value": "-23%", "change": "" }
  ],
  "chart": {
    "labels": ["Jan", "Feb", "Mar"],
    "datasets": [{ "label": "Revenue", "data": [2070000, 1836000, 1950000] }]
  },
  "chart_type": "bar",
  "from_cache": false,
  "corrected": false,
  "latency_ms": 1847,
  "session_id": "user-001"
}
```

### Streaming Query

```bash
# SSE streaming — tokens arrive word-by-word
curl -N "http://localhost:8000/api/query/stream?query=Why+did+sales+drop%3F&session_id=user-001" \
  -H "Authorization: Bearer $TOKEN"

# Event stream output:
# event: token
# data: {"token": "Sales "}
# event: token
# data: {"token": "dropped "}
# event: metadata
# data: {"engine": "analytical", "sources": [...], "chart": {...}, "latency_ms": 1920}
# event: done
# data: {}
```

---

## 🔒 RBAC & Onboarding Guide

### Role Hierarchy

```
admin            → All views and columns (*) — no restrictions
regional_manager → Region-filtered aggregated views, no PII
analyst          → Aggregated metrics views only, no row-level data
auditor          → Audit trail tables only
viewer           → Summary dashboard views only
```

### How Role-Based Security Works

1. **JWT** is issued with the user's role embedded in claims
2. On each request, `rbac.py` loads the **list of views** the role is allowed to access
3. The **schema of only those views** is serialized into a string
4. That schema string is **injected into the LLM's system prompt** — the LLM physically cannot reference tables or columns it hasn't been told about
5. Even if an attacker extracts the LLM prompt, the schema contains only read-only views
6. **SQL safety check** additionally blocks any DML/DDL regardless of what the LLM generates

### Configuring Roles (Technical)

In Supabase SQL Editor, create filtered views:

```sql
-- Analyst view: aggregated only, no PII
CREATE OR REPLACE VIEW analyst_sales_view AS
SELECT
    region,
    product_category,
    DATE_TRUNC('month', sale_date) AS month,
    SUM(revenue) AS total_revenue,
    COUNT(*) AS transaction_count,
    AVG(revenue) AS avg_order_value
FROM sales_fact
GROUP BY region, product_category, month;

-- Grant read-only to analyst role
GRANT SELECT ON analyst_sales_view TO analyst_role;

-- Regional manager: filtered by region
CREATE OR REPLACE VIEW rm_sales_view AS
SELECT
    product_category,
    DATE_TRUNC('week', sale_date) AS week,
    SUM(revenue) AS total_revenue
FROM sales_fact
WHERE region = current_setting('app.user_region', true)
GROUP BY product_category, week;
```

Register the role in `backend/core/rbac.py`:

```python
ROLE_SCHEMA_MAP = {
    "admin":            ["*"],                              # All tables
    "analyst":          ["analyst_sales_view", "analyst_kpi_view"],
    "regional_manager": ["rm_sales_view", "rm_customer_view"],
    "auditor":          ["audit_trail_view"],
    "viewer":           ["dashboard_summary_view"],
}
```

The LLM context manager automatically injects only the role's schema — zero code changes needed.

### Non-Technical Onboarding (CSV)

1. `POST /api/schema/onboard` with your CSV file
2. UQS auto-detects column names, infers data types, and proposes a schema
3. LLM suggests predictive targets (e.g., "the `churn` column looks like a classification target")
4. LLM proposes RBAC views for common roles
5. Confirm or edit the schema — tables are created in your Supabase instance

---

## 📊 Development Status

### ✅ Fully Implemented & Working

**Infrastructure**
- [x] `backend/config.py` — Pydantic settings from environment
- [x] `backend/core/database.py` — Supabase async PostgreSQL connection
- [x] `backend/core/auth.py` — JWT auth with role extraction
- [x] `backend/core/rbac.py` — Role → view mapping + schema string injection
- [x] `backend/core/logger.py` — Structured JSON audit trail
- [x] `backend/core/security.py` — Rate limiter, input sanitizer, SQL blocklist

**LangGraph Pipeline** ⭐
- [x] `backend/graph/state.py` — `UQSState` TypedDict (full pipeline state)
- [x] `backend/graph/nodes.py` — 8 async nodes with timeout guards + error handling
- [x] `backend/graph/pipeline.py` — Compiled `StateGraph` singleton with conditional edges
- [x] LangGraph replaces all `if/elif` routing in `api/query.py`

**LLM Layer**
- [x] `backend/llm/client.py` — Pluggable client (Ollama / OpenAI / Anthropic)
- [x] `backend/llm/context_manager.py` — Per-user session store with schema injection
- [x] `backend/llm/prompts/all_prompts.py` — 7 system prompts (classifier, SQL, analytical, RAG, formatter, cache, schema)

**AI Engines**
- [x] `backend/engines/classifier.py` — Query Classification Engine (LLM-based)
- [x] `backend/engines/sql_engine.py` — NL→SQL with DIN-SQL + self-correction loop
- [x] `backend/engines/analytical_engine.py` — Algorithm brain + parallel SQL orchestration
- [x] `backend/engines/predictive_engine.py` — Multi-model pool + auto-selection + inference
- [x] `backend/engines/rag_engine.py` — FAISS vector retrieval + grounded answers
- [x] `backend/engines/rag_plus_plus.py` — Hybrid DB + document context merging

**Cache Intelligence**
- [x] `backend/cache/cache_manager.py` — 4-granularity FIFO cache (hourly/daily/weekly/monthly)
- [x] `backend/cache/cache_query.py` — LLM-assisted semantic cache hit detection
- [x] `backend/cache/cron_generator.py` — APScheduler background report generation

**ML Registry & Learning**
- [x] `backend/models/registry.py` — Versioned model storage + rollback
- [x] `backend/models/trainer.py` — Multi-model training pool
- [x] `backend/models/evaluator.py` — Automated model selection by metric
- [x] `backend/models/continual_learning.py` — Daily cron retraining + auto-promote

**Vector Store**
- [x] `backend/vector_store/store.py` — FAISS index with numpy fallback
- [x] `backend/vector_store/ingestion.py` — PDF/DOCX/TXT chunking pipeline

**API Layer**
- [x] `POST /api/query` — Full JSON response
- [x] `GET /api/query/stream` — **SSE token-by-token streaming** with fallback
- [x] `POST /api/documents/upload` — RAG document ingestion
- [x] `POST /api/schema/onboard` — CSV onboarding with LLM schema proposal
- [x] Admin endpoints: cache flush, model rollback, manual retrain

**Frontend (Next.js 16)**
- [x] Premium dark-mode design system (glassmorphism, ambient blobs, gradients)
- [x] `ChatInterface.tsx` — SSE streaming with blinking cursor + stop button
- [x] `ResponseCard.tsx` — Metrics grid, copy button, latency display, raw JSON toggle
- [x] `ChartRenderer.tsx` — Bar/Line/Pie/Table/Predictions charts (Recharts)
- [x] `DocumentUpload.tsx` — Drag-and-drop with progress states
- [x] `CacheStatusPanel.tsx` — 4-granularity fill bars + report summaries
- [x] `ModelStatus.tsx` — Version pills, metrics, feature list
- [x] 5-tab layout: Chat · Cache · Models · Engines · RBAC
- [x] Auth modal with dev role selection + JWT flow
- [x] Health check indicator in sidebar

**Competition Compliance**
- [x] `README.md` — This file
- [x] `CONTRIBUTING.md` — DCO sign-off guide
- [x] `LICENSE` — Apache 2.0
- [x] `.env.example` — No real credentials
- [x] `docs/architecture.md` — Full Mermaid data-flow diagrams
- [x] `backend/tests/test_core.py` — Unit tests

### ⚠️ Known Limitations

| Limitation | Status | Notes |
|---|---|---|
| Docker Compose | Not included | All services start manually; structure is ready |
| Supabase RLS | App-level only | Supabase Row Level Security requires manual policy setup |
| True LLM token streaming | Word-level simulation | Native per-token streaming needs provider-specific support |
| Redis cache backend | File-based JSON | Redis-ready architecture; swap `cache_manager.py` |
| Qdrant vector store | FAISS local only | Config supports Qdrant; needs Docker |
| Multi-tenant isolation | Session scoping | Full tenant isolation needs Redis |

### 🚧 Future Roadmap

- [ ] Docker Compose — one-command startup
- [ ] Redis cache backend
- [ ] Qdrant vector DB integration
- [ ] True incremental continual learning (PEFT / EWC)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Multi-tenant SaaS deployment
- [ ] Voice input support
- [ ] Snowflake / BigQuery connectors

---

## 🧰 Technology Stack

| Layer | Technology | Why Chosen |
|---|---|---|
| **Pipeline Orchestration** | LangGraph 0.2 | Stateful graph — visual, resumable, per-node timeouts, fault-tolerant |
| **LLM (local)** | Gemma 2B via Ollama | Lightweight (2B params), free, runs fully local, swappable |
| **LLM (cloud options)** | OpenAI / Anthropic | Pluggable via env var `LLM_PROVIDER` |
| **NL→SQL** | DIN-SQL / DAIL-SQL patterns | SOTA text-to-SQL (published 2023-24), schema linking step |
| **API Framework** | FastAPI + Uvicorn | Async, auto OpenAPI, native SSE/Streaming support |
| **Database** | Supabase (PostgreSQL) | Managed, RBAC-friendly, free tier generous |
| **Vector Store** | FAISS (→ Qdrant) | Zero infra for hackathon; Qdrant config ready for scale |
| **Embeddings** | all-MiniLM-L6-v2 | 22M params, 384-dim, fast, highly accurate, fully local |
| **ML Models** | XGBoost, LightGBM, RandomForest, Prophet | Battle-tested, best-in-class for tabular + time-series |
| **Rate Limiting** | SlowAPI | Production-grade, FastAPI-native, configurable per-IP |
| **Scheduling** | APScheduler | Built-in FastAPI integration, no Celery overhead |
| **Frontend** | Next.js 16 (App Router) | SSR, TypeScript strict, native SSE fetch support |
| **UI Styling** | Vanilla CSS | Full design control, ~600 lines custom dark theme |
| **Charts** | Recharts | Lightweight, composable, React-native, fully typed |
| **Auth** | JWT (python-jose) | Stateless, role-carrying tokens, zero session store |

---

## 🤝 Contributing & DCO

This project uses the **Developer Certificate of Origin (DCO)**.

All commits must be signed:

```bash
git commit -s -m "feat: describe your change"
```

The `-s` flag adds `Signed-off-by: Hitesh Mehta <hteshpooja@gmail.com>` to your commit.

**Pull Request flow:**
1. Fork the repository
2. Create a branch: `git checkout -b feat/my-feature`
3. Make your changes (with comments and type hints)
4. Sign your commits: `git commit -s -m "feat: my feature"`
5. Push: `git push origin feat/my-feature`
6. Open a PR with a clear description

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full guidelines.

---

## 📊 Presentation

- 📥 [Download PPT](./UQS_Zenith_NatWest_2026.pptx)

---

## 📄 License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

> Built with ❤️ for the **NatWest Hackathon — Talk to Data: Seamless Self-Service Intelligence**
>
> All code is original. Open-source libraries are used per their respective licenses.
>
> ### **Clarity · Trust · Speed**
