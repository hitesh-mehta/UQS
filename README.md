# 🧠 Universal Query Solver (UQS)

> **AI-Driven Data Warehouse & Business Intelligence Platform**
> Hackathon Submission — NatWest Group: *Talk to Data: Seamless Self-Service Intelligence*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14%2B-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

---

## 📋 Table of Contents

1. [What is UQS?](#-what-is-uqs)
2. [The Three Pillars](#-the-three-pillars)
3. [System Architecture](#-system-architecture)
4. [Core Engines](#-core-engines)
5. [File Structure](#-file-structure)
6. [Prerequisites](#-prerequisites)
7. [Installation & Setup](#-installation--setup)
8. [Environment Variables](#-environment-variables)
9. [Running the Project](#-running-the-project)
10. [API Reference](#-api-reference)
11. [RBAC & Onboarding Guide](#-rbac--onboarding-guide)
12. [Development Status](#-development-status)
13. [Technology Stack](#-technology-stack)
14. [Contributing](#-contributing)

---

## 🚀 What is UQS?

**Universal Query Solver (UQS)** is an AI-native Business Intelligence platform that lets any user — technical or non-technical — ask questions about enterprise data in plain English and receive instant, accurate, cited answers.

It eliminates the need for SQL knowledge, data science expertise, or navigating complex BI dashboards. Behind a single conversational interface, UQS orchestrates five specialized AI engines, enforces database-level Role-Based Access Control (RBAC), and intelligently caches reports to serve the majority of queries near-instantly.

### Key Differentiators

| Feature | Description |
|---|---|
| 🗣️ **Single NL Interface** | One chat box for SQL queries, analytics, predictions, and document Q&A |
| 🔐 **DB-Level RBAC** | Roles map to read-only PostgreSQL views — LLM never sees unauthorized data |
| ⚡ **Cache Intelligence** | Pre-generated hourly/daily/weekly/monthly reports served in milliseconds |
| 🤖 **5 Specialized Engines** | SQL, Analytical, Predictive, RAG, RAG++ — each optimal for its query type |
| 📊 **Explainable AI** | Every answer cites source tables, documents, and reasoning |
| 🔄 **Continual Learning** | ML models retrain daily; versioned with admin rollback up to 5 versions |

---

## 🎯 The Three Pillars

### ✅ Clarity
- LLM-generated plain-English answers — no SQL or jargon exposed to users
- Every response includes a narrative description + visual (table/chart)
- Consistent metric definitions enforced via schema and prompt engineering

### ✅ Trust
- Every response cites the exact source table, view, or document used
- RBAC ensures users only ever see data within their authorization scope
- All queries and LLM calls are logged for full audit trails
- SQL injection prevention via parameterized queries + LLM output validation

### ✅ Speed
- Cache Intelligence Layer serves repeated queries in near real-time (~milliseconds)
- Lightweight local LLM (Gemma 2B) minimizes inference latency
- Parallel SQL sub-queries in the Analytical Engine reduce wait times

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE LAYER                        │
│              Natural Language Chat UI (Next.js)                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP / WebSocket
┌───────────────────────────────▼──────────────────────────────────────┐
│                        FASTAPI GATEWAY LAYER                         │
│       Auth (JWT) → Role Identification → Context Loading             │
└──────────┬──────────────────────────────────────┬────────────────────┘
           │                                      │
┌──────────▼──────────┐               ┌───────────▼────────────────────┐
│  RBAC / View Engine │               │   LLM Context Manager          │
│  (Supabase views,   │               │   (Schema-aware per role,      │
│  read-only, no DML) │               │   per-user session store)      │
└──────────┬──────────┘               └───────────┬────────────────────┘
           │                                      │
┌──────────▼──────────────────────────────────────▼────────────────────┐
│                   QUERY CLASSIFICATION ENGINE (LLM)                  │
│   Irrelevant ──► Polite Rejection                                    │
│   Relevant   ──► {SQL | Analytical | Predictive | RAG | RAG++}      │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
          ┌────────────▼─────────────┐
          │    CACHE INTELLIGENCE    │  LLM checks if query hits
          │    (4-granularity FIFO)  │  hourly/daily/weekly/monthly cache
          └──────┬───────────────────┘
                 │
        ─────────┴──────────────────────────────────────────
       │                   │              │                 │
       ▼                   ▼              ▼                 ▼
  ┌─────────┐       ┌──────────┐   ┌──────────┐    ┌──────────────┐
  │   SQL   │       │Analytical│   │Predictive│    │  RAG / RAG++ │
  │ Engine  │       │  Engine  │   │  Engine  │    │   Engine     │
  └────┬────┘       └────┬─────┘   └────┬─────┘    └──────┬───────┘
       │                 │              │                  │
       └─────────────────┴──────────────┴──────────────────┘
                                   │
                         ┌─────────▼──────────┐
                         │  RESPONSE FORMATTER │
                         │  (LLM + Templates)  │
                         └─────────┬───────────┘
                                   │
                         ┌─────────▼──────────┐
                         │   UI: Text + Charts │
                         │   + Source Refs     │
                         └────────────────────┘
```

### End-to-End Data Flow

```
User Query
    │
    ├─ 1. Auth & RBAC     → identify role, load role-scoped schema
    ├─ 2. Classification  → LLM: relevant? what type?
    ├─ 3. Cache Check     → LLM: can any cached report answer this?
    │       ├─ HIT  → return cached answer (< 100ms)
    │       └─ MISS → route to engine
    ├─ 4. Engine Routing  → SQL / Analytical / Predictive / RAG / RAG++
    ├─ 5. Execution       → DB query / ML inference / vector retrieval
    ├─ 6. Formatting      → LLM: narrative + table/chart + source refs
    └─ 7. Response        → JSON to frontend
```

---

## ⚙️ Core Engines

### 1. 🔍 SQL Engine
Converts natural language to SQL using SOTA [DIN-SQL](https://arxiv.org/abs/2304.11015) / [DAIL-SQL](https://arxiv.org/abs/2308.15363) patterns:

- **Schema Injection** — role-scoped schema embedded in LLM context
- **Schema Linking** — LLM identifies relevant tables/columns before writing SQL
- **Self-Correction Loop** — SQL errors fed back to LLM for one retry
- **Safety Validation** — blocks any DELETE/UPDATE/INSERT/DROP
- **Result Explanation** — raw results always accompanied by plain-English summary

### 2. 📈 Analytical Engine
Sits on top of the SQL Engine to answer complex, insight-oriented questions:

| Sub-type | Example |
|---|---|
| Trend Analysis | "How has revenue trended over 6 months?" |
| Causal / Diagnostic | "Why did churn increase in March?" |
| Comparative | "How does Region A compare to Region B?" |
| What-If / Scenario | "What if we reduce ad spend by 20%?" |
| Time-Series | "Show the weekly pattern in support tickets" |
| Decomposition | "Break down total costs by department" |

The LLM acts as an **Algorithm Brain** — it deconstructs complex queries, selects statistical methods, orchestrates parallel SQL calls, and synthesizes results into coherent narratives.

### 3. 🔮 Predictive Engine
Zero-expertise ML forecasting, clustering, and anomaly detection:

- **Multi-Model Training Pool** — XGBoost, RandomForest, LSTM, Prophet, IsolationForest
- **Automated Model Selection** — best model by RMSE/F1/AUC/Silhouette
- **Hyperparameter Tuning** — Grid/Random/Bayesian search
- **Model Registry** — versioned (v1, v2, ...) with `active` pointer
- **Continual Learning** — daily cron retraining; auto-promote if performance improves
- **Admin Rollback** — up to 5 version lookback, with dataset cleanup

```
models/
├── target_revenue/
│   ├── v1/  (model + metadata + dataset hash)
│   ├── v2/  (updated model)
│   └── active → v2         # symlink to best version
└── target_churn/
    └── v1/
```

### 4. 📄 RAG Engine
Ground answers in user-uploaded documents (PDF, DOCX, TXT):

```
Document → Chunking → Embeddings (all-MiniLM-L6-v2) → FAISS Index
User Query → Embed → Top-K Similarity Search → LLM Answer + Source Refs
```

### 5. 🔗 RAG++ Engine
Hybrid answers combining live DB data + uploaded documents:

```
User Query
    ├── SQL Engine     → fetch relevant DB data
    └── RAG Engine     → retrieve document chunks
              ↓
    Context Merging → LLM Synthesis
              ↓
    Answer references both DB tables and document pages
```

---

## 📁 File Structure

```
UQS/
├── README.md                          ← You are here
├── .env.example                       ← Copy to .env and fill in values
├── .gitignore
│
├── backend/                           ← FastAPI Python backend (main brain)
│   ├── main.py                        ← FastAPI app entrypoint
│   ├── requirements.txt               ← Python dependencies
│   ├── config.py                      ← Pydantic settings from .env
│   │
│   ├── core/                          ← Core infrastructure
│   │   ├── database.py                ← Supabase/PostgreSQL async connection
│   │   ├── auth.py                    ← JWT authentication & role extraction
│   │   ├── rbac.py                    ← Role → DB view mapping + schema loader
│   │   └── logger.py                  ← Structured audit trail logging
│   │
│   ├── engines/                       ← The 5 specialized AI engines
│   │   ├── classifier.py              ← Query Classification Engine
│   │   ├── sql_engine.py              ← NL→SQL pipeline (SOTA)
│   │   ├── analytical_engine.py       ← Algorithm brain for complex insights
│   │   ├── predictive_engine.py       ← ML inference & model management
│   │   ├── rag_engine.py              ← Document Q&A via vector retrieval
│   │   └── rag_plus_plus.py           ← Hybrid DB + document context
│   │
│   ├── cache/                         ← Cache Intelligence Layer
│   │   ├── cache_manager.py           ← FIFO report cache (4 granularities)
│   │   ├── cache_query.py             ← LLM-assisted cache hit detection
│   │   └── cron_generator.py          ← Scheduled report generation
│   │
│   ├── llm/                           ← LLM abstraction layer
│   │   ├── client.py                  ← Pluggable LLM client (Gemma/Mistral/etc.)
│   │   ├── context_manager.py         ← Per-user schema + session context store
│   │   └── prompts/                   ← All system prompts (versioned)
│   │       ├── classifier_prompt.py
│   │       ├── sql_prompt.py
│   │       ├── analytical_prompt.py
│   │       ├── predictive_prompt.py
│   │       ├── rag_prompt.py
│   │       └── formatter_prompt.py
│   │
│   ├── models/                        ← ML Model Registry & Lifecycle
│   │   ├── registry.py                ← Versioned model storage & rollback
│   │   ├── trainer.py                 ← Multi-model training pool
│   │   ├── evaluator.py               ← Metrics & automated model selection
│   │   └── continual_learning.py      ← Daily cron retraining pipeline
│   │
│   ├── vector_store/                  ← RAG vector storage layer
│   │   ├── embedder.py                ← sentence-transformers embedding
│   │   ├── store.py                   ← FAISS index abstraction
│   │   └── ingestion.py               ← PDF/doc chunking & indexing pipeline
│   │
│   ├── schema/                        ← Schema management & onboarding
│   │   ├── onboarding.py              ← CSV auto-detect + LLM schema proposal
│   │   ├── rbac_views.py              ← Dynamic DB view creation per role
│   │   └── metric_dict.py             ← Domain terminology dictionary
│   │
│   ├── api/                           ← FastAPI route handlers
│   │   ├── query.py                   ← POST /api/query — main query endpoint
│   │   ├── documents.py               ← POST /api/documents — RAG file upload
│   │   ├── models_api.py              ← GET/POST /api/models
│   │   ├── cache_api.py               ← GET /api/cache — cache status
│   │   ├── schema_api.py              ← POST /api/schema — onboarding
│   │   └── admin.py                   ← Admin: rollback, cache flush
│   │
│   └── tests/                         ← Unit & integration tests
│       ├── test_classifier.py
│       ├── test_sql_engine.py
│       ├── test_cache.py
│       ├── test_predictive.py
│       └── test_rag.py
│
├── frontend/                          ← Next.js 14 frontend
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx                 ← Root layout with providers
│   │   ├── page.tsx                   ← Landing / chat UI
│   │   └── globals.css                ← Global styles
│   ├── components/
│   │   ├── ChatInterface.tsx           ← Main NL query input + response
│   │   ├── ResponseCard.tsx            ← Text + chart + source references
│   │   ├── SourceBadge.tsx             ← "Source: table_name" chips
│   │   ├── QueryTypeIndicator.tsx      ← Engine badge (SQL/Analytical/etc.)
│   │   ├── ChartRenderer.tsx           ← Recharts-based data visualization
│   │   └── ModelStatus.tsx             ← ML model registry status widget
│   └── lib/
│       ├── api.ts                      ← Typed API client to backend
│       └── types.ts                    ← Shared TypeScript types
│
├── scripts/
│   ├── init_db.py                     ← DB schema + RBAC view initialization
│   ├── seed_cache.py                  ← Generate initial report cache
│   └── seed_models.py                 ← Trigger initial ML model training
│
└── docs/
    ├── architecture.md                ← Detailed diagrams & design decisions
    ├── rbac_guide.md                  ← How to configure roles and views
    ├── api_reference.md               ← Full REST API documentation
    └── deployment.md                  ← Docker / production deployment guide
```

---

## ✅ Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| Ollama | Latest | Local LLM runtime |
| Gemma 2B / 7B | via Ollama | `ollama pull gemma2:2b` |
| Supabase Account | — | Free tier sufficient for dev |
| Git | 2.x+ | Version control |

### Install Ollama
```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma2:2b

# Windows: download from https://ollama.com/download
ollama pull gemma2:2b
```

---

## 🛠️ Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/hitesh-mehta/UQS
cd uqs
```

### 2. Backend Setup
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd frontend
npm install
```

### 4. Configure Environment
```bash
# From project root
cp .env.example .env
# Edit .env with your Supabase credentials
```

### 5. Initialize the Database
```bash
cd backend
python -m scripts.init_db
```

### 6. (Optional) Seed Initial Cache & Models
```bash
python -m scripts.seed_cache
python -m scripts.seed_models
```

---

## 🔐 Environment Variables

Copy `.env.example` to `.env`:

```env
# ── Supabase ──────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# ── LLM ───────────────────────────────────────────
LLM_PROVIDER=ollama                 # ollama | openai | anthropic
LLM_MODEL=gemma2:2b                 # gemma2:2b | mistral | llama3.2
LLM_BASE_URL=http://localhost:11434 # Ollama default

# ── Embeddings ────────────────────────────────────
EMBEDDING_MODEL=all-MiniLM-L6-v2   # sentence-transformers model name

# ── Auth ──────────────────────────────────────────
JWT_SECRET=your-very-long-random-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ── Cache ─────────────────────────────────────────
CACHE_STORE_PATH=./cache_store      # local filesystem cache
CACHE_RETENTION_UNITS=10            # 10 hourly / 10 daily / 10 weekly / 10 monthly

# ── ML Models ─────────────────────────────────────
MODEL_REGISTRY_PATH=./model_registry
MAX_ROLLBACK_VERSIONS=5

# ── Vector Store ──────────────────────────────────
VECTOR_STORE_TYPE=faiss             # faiss | qdrant
FAISS_INDEX_PATH=./faiss_index

# ── API ───────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true
```

---

## ▶️ Running the Project

### Development Mode

**Terminal 1 — LLM (Ollama)**
```bash
ollama serve
```

**Terminal 2 — Backend**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 — Frontend**
```bash
cd frontend
npm run dev
```

Then open: **http://localhost:3000**

API docs (auto-generated): **http://localhost:8000/docs**

### Running Tests
```bash
cd backend
pytest tests/ -v
```

---

## 📡 API Reference

### Core Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `POST` | `/api/query` | Submit a natural language query | ✅ JWT |
| `POST` | `/api/documents` | Upload document for RAG ingestion | ✅ JWT |
| `GET` | `/api/cache/status` | View cache contents & hit rates | ✅ JWT |
| `POST` | `/api/schema/onboard` | Onboard new dataset (CSV or DB) | ✅ Admin |
| `GET` | `/api/models` | List all ML models and versions | ✅ JWT |
| `POST` | `/api/models/rollback` | Roll back a target model | ✅ Admin |
| `POST` | `/api/admin/cache/flush` | Flush all cache | ✅ Admin |

### Query Request/Response

**Request:**
```json
POST /api/query
{
  "query": "Why did sales drop in February?",
  "session_id": "user-session-uuid"
}
```

**Response:**
```json
{
  "answer": "Sales dropped 11% in February. The primary driver was...",
  "engine": "analytical",
  "query_type": "causal_diagnostic",
  "sources": ["sales_fact_view", "region_dim_view"],
  "chart": {
    "type": "bar",
    "data": [...]
  },
  "from_cache": false,
  "latency_ms": 1240
}
```

---

## 🔒 RBAC & Onboarding Guide

### Role Hierarchy

```
Admin            → Full schema access (all tables + all columns)
Regional Manager → Filtered by region; no PII columns
Analyst          → Aggregated views only; no row-level data
External Auditor → Specific audit-trail tables only
```

### Configuring Roles (Technical Onboarding)

1. In Supabase SQL Editor, create filtered views per role:
```sql
-- Example: Analyst view (aggregated only, no PII)
CREATE VIEW analyst_sales_view AS
SELECT
    region,
    product_category,
    DATE_TRUNC('month', sale_date) AS month,
    SUM(revenue) AS total_revenue,
    COUNT(*) AS transaction_count
FROM sales_fact
GROUP BY region, product_category, month;

-- Grant read-only access
GRANT SELECT ON analyst_sales_view TO analyst_role;
```

2. Register the role in `backend/core/rbac.py`:
```python
ROLE_SCHEMA_MAP = {
    "admin": ["*"],               # all tables
    "analyst": ["analyst_sales_view", "analyst_kpi_view"],
    "regional_manager": ["rm_sales_view", "rm_customer_view"],
    "auditor": ["audit_trail_view"],
}
```

3. The LLM context manager automatically injects only the role's schema.

### Non-Technical Onboarding (CSV)

1. Call `POST /api/schema/onboard` with your CSV file
2. UQS auto-detects column names, data types, and proposes a schema
3. Confirm or edit the schema via API response
4. RBAC defaults to single-user full access
5. Predictive targets are proposed interactively

---

## 📊 Development Status

### ✅ Completed
- [x] Project architecture & documentation
- [x] File structure scaffolding
- [x] `core/database.py` — Supabase async connection
- [x] `core/auth.py` — JWT authentication
- [x] `core/rbac.py` — Role → view mapping
- [x] `core/logger.py` — Audit logging
- [x] `llm/client.py` — Pluggable LLM client (Ollama/OpenAI)
- [x] `llm/context_manager.py` — Per-user session store with schema injection
- [x] `llm/prompts/` — All system prompts (classifier, SQL, analytical, RAG, formatter)
- [x] `engines/classifier.py` — Query Classification Engine
- [x] `engines/sql_engine.py` — NL→SQL with DIN-SQL patterns + self-correction
- [x] `engines/analytical_engine.py` — Algorithm brain + parallel SQL orchestration
- [x] `engines/predictive_engine.py` — Multi-model training pool + inference
- [x] `engines/rag_engine.py` — Document ingestion + FAISS vector search
- [x] `engines/rag_plus_plus.py` — Hybrid DB + document context merging
- [x] `cache/cache_manager.py` — 4-granularity FIFO report cache
- [x] `cache/cache_query.py` — LLM-assisted cache hit detection
- [x] `cache/cron_generator.py` — Scheduled report generation
- [x] `models/registry.py` — Model versioning & rollback
- [x] `models/trainer.py` — Multi-model pool (XGBoost, RF, Prophet, LSTM)
- [x] `models/evaluator.py` — Automated model selection
- [x] `models/continual_learning.py` — Daily retraining pipeline
- [x] `vector_store/` — FAISS embedding & retrieval
- [x] `schema/` — Onboarding & RBAC view management
- [x] `api/` — All FastAPI route handlers
- [x] `main.py` — FastAPI application entrypoint
- [x] `scripts/init_db.py` — DB initialization script

### 🔄 In Progress / Next Steps
- [ ] Frontend — Next.js Chat UI with ResponseCard & ChartRenderer
- [ ] Cron job scheduling integration (Celery/APScheduler)
- [ ] Docker Compose for one-command deployment
- [ ] Redis cache backend (upgrade from local filesystem)
- [ ] Qdrant vector DB integration (upgrade from FAISS)
- [ ] End-to-end integration tests
- [ ] CI/CD pipeline (GitHub Actions)

### 🚧 Future Roadmap
- [ ] True incremental continual learning (PEFT / EWC)
- [ ] Multi-tenant SaaS deployment
- [ ] Streaming responses (Server-Sent Events)
- [ ] Voice input support
- [ ] Mobile app (React Native)
- [ ] Snowflake / BigQuery connectors

---

## 🧰 Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **LLM** | Gemma 2B via Ollama | Lightweight, free, local, swappable |
| **NL→SQL** | DIN-SQL / DAIL-SQL patterns | SOTA Text-to-SQL (2024) |
| **API Framework** | FastAPI | Async, fast, OpenAPI docs auto-generated |
| **Database** | Supabase (PostgreSQL) | Managed, RBAC-friendly, real-time capable |
| **Vector DB** | FAISS (→ Qdrant) | Zero infra for hackathon; Qdrant for scale |
| **Embeddings** | `all-MiniLM-L6-v2` | 22M params, fast, highly accurate |
| **ML Models** | XGBoost, RandomForest, LightGBM, Prophet, LSTM | Battle-tested SOTA ensemble |
| **Orchestration** | Custom async pipeline (asyncio) | Explicit, debuggable, no framework overhead |
| **Cache** | Filesystem JSON (→ Redis) | Simple for hackathon; Redis-ready |
| **Frontend** | Next.js 14 (App Router) | SSR, TypeScript, great DX |
| **Charts** | Recharts | Lightweight, composable, React-native |
| **Auth** | JWT (python-jose) | Stateless, role-carrying tokens |

---

## 🤝 Contributing

This is a hackathon submission. For questions or collaboration:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add: my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

Apache 2.0 License — see [LICENSE](LICENSE) for details.

---

> Built with ❤️ for the NatWest Hackathon | *Talk to Data: Seamless Self-Service Intelligence*
>
> **Clarity · Trust · Speed**
