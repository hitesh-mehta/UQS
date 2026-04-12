# UQS Architecture

## Full Data-Flow Diagram

```mermaid
flowchart TD
    U([User]) -->|Natural Language Query| FE[Next.js Chat UI\nStreaming SSE]
    FE -->|POST /api/query\nGET /api/query/stream| MW

    subgraph Backend ["FastAPI Backend"]
        MW["Middleware Stack\n• JWT Auth\n• RBAC Schema Injection\n• Rate Limiter 30/min\n• Input Sanitizer\n• Timeout Guard 30s"]
        MW --> LG

        subgraph LG ["LangGraph StateGraph Pipeline"]
            C[classify\nQueryClassifier]
            CC[check_cache\nLLM cache-hit detection]
            SQL[SQL Engine\nDIN-SQL + Self-Correction]
            ANA[Analytical Engine\nAlgorithm Brain]
            PRED[Predictive Engine\nXGBoost/RF/Prophet]
            RAG[RAG Engine\nFAISS Vector Search]
            RAGPP[RAG++ Engine\nHybrid DB + Docs]
            FMT[format_response]

            C -->|relevant| CC
            C -->|irrelevant| FMT
            CC -->|cache hit| FMT
            CC -->|sql| SQL
            CC -->|analytical| ANA
            CC -->|predictive| PRED
            CC -->|rag| RAG
            CC -->|rag++| RAGPP
            SQL --> FMT
            ANA --> FMT
            PRED --> FMT
            RAG --> FMT
            RAGPP --> FMT
        end

        subgraph Data ["Data Layer"]
            DB[(Supabase\nPostgreSQL)]
            VS[(FAISS\nVector Store)]
            MR[(Model\nRegistry)]
            CACHE[(FIFO\nReport Cache)]
        end

        SQL <-->|RBAC-gated views| DB
        ANA <-->|RBAC-gated views| DB
        PRED <-->|ML inference| MR
        RAG <-->|semantic search| VS
        RAGPP <-->|both| DB
        RAGPP <-->|both| VS
        CC <-->|summaries| CACHE
    end

    FMT -->|SSE token stream\nor JSON| FE

    subgraph Cron ["Background Jobs (APScheduler)"]
        CG[Cron Report Generator\nhourly/daily/weekly/monthly]
        CL[Continual Learning\ndaily model retraining]
    end
    CG --> CACHE
    CL --> MR
```

## RBAC Security Contract

```
Role         → DB Views Accessible
────────────────────────────────────────────────────────────────
admin        → all views (*)
analyst      → analyst_sales_view, analyst_kpi_view
reg_manager  → rm_sales_view, rm_customer_view
auditor      → audit_trail_view
viewer       → dashboard_summary_view
────────────────────────────────────────────────────────────────

Enforcement chain:
  JWT token (role field)
    → rbac.py loads schema for that role ONLY
    → schema injected into LLM system prompt
    → LLM physically cannot reference other tables
    → SQL safety check blocks DML/DDL regardless
```

## LangGraph State Machine

```
UQSState = TypedDict {
  query, session_id, session, audit, user     ← inputs
  query_type, relevant, polite_rejection      ← from classify
  cache_hit, cache_answer, cache_source       ← from check_cache
  engine_answer, engine_sources, engine_chart ← from engine nodes
  final_response                              ← assembled by format
  error, retry_count                          ← error handling
}

Node timeout: 28 seconds each
Cache check timeout: 5 seconds (fast-fail safe)
```

## Cache FIFO Policy

```
Granularity  Retention  Eviction
──────────────────────────────────
hourly       10 units   FIFO
daily        10 units   FIFO
weekly       10 units   FIFO
monthly      10 units   FIFO

When the 11th unit is added, the oldest (1st) is deleted.
LLM compares incoming query against cache summaries
to determine semantic cache hit (not exact-match).
```

## SQL Self-Correction Loop

```
NL Query
  → Schema linking (identify relevant views)
  → LLM generates SQL
  → Safety check (expanded blocklist)
  → Execute against DB
  ↓ if error:
  → Feed error message back to LLM
  → LLM corrects SQL
  → Execute again
  ↓ if 2nd failure:
  → Return graceful error message
```

## Predictive Engine — Model Selection

```
Task detected → Training pool:
  regression   → [XGBoost, RandomForest, LightGBM]  → lowest RMSE wins
  classification → [XGBoost, RF, LightGBM]           → highest F1 wins
  forecasting  → [Prophet, ARIMA]                    → lowest MAE wins
  clustering   → [KMeans, DBSCAN]                    → highest silhouette wins
  anomaly      → [IsolationForest]                   → auto

Daily retraining:
  new model trained → metrics compared → auto-promote if improved
                                      → rollback retained if not
```
