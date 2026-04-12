# UQS Architecture Deep Dive

## System Architecture

```
User NL Query → JWT Auth → RBAC View Load → Query Classifier → Cache Check
    → Route: SQL | Analytical | Predictive | RAG | RAG++
    → Response Formatter → UI (text + chart + source refs)
```

## RBAC Security Contract

1. All DB views are created at initialization time by a technical admin
2. Views are read-only — no role has INSERT/UPDATE/DELETE privileges
3. LLM context manager ONLY injects the schema for the current user's role
4. LLM is physically incapable of referencing tables/columns outside its schema context

## Cache FIFO Policy

```
granularity: hourly | daily | weekly | monthly
retention:   10 units each
eviction:    when 11th unit added → oldest (1st) is deleted

Example for daily:
  Day 1:  [report_2024-01-01]
  Day 2:  [report_2024-01-01, report_2024-01-02]
  ...
  Day 10: [10 reports]
  Day 11: [reports 2–11] ← Day 1 report evicted
```

## Self-Correction SQL Loop

```
NL Query → LLM generates SQL → Safety check (block DML/DDL)
    → Execute SQL
    → If error: feed error back to LLM → LLM corrects SQL → Execute again
    → If 2nd failure: raise HTTPException (don't attempt further)
```

## Model Registry Versioning

```
model_registry/
  target_revenue/
    v1/ model.pkl + metadata.json + dataset_hash.txt
    v2/ model.pkl + metadata.json + dataset_hash.txt
    active.txt → "2"   ← symlink-like pointer file
  target_churn/
    v1/ ...
    active.txt → "1"
```

## Embeddings Pipeline (RAG)

```
Document (PDF/DOCX/TXT)
  → pymupdf/pypdf/python-docx (text extraction)
  → chunk_text(size=500, overlap=100)  ← overlapping chunks preserve context
  → SentenceTransformer.encode() → 384-dim vector
  → faiss.IndexFlatIP.add() ← inner product = cosine sim for normalized vectors
  → Persist to disk (faiss_index/)

Query
  → SentenceTransformer.encode()
  → faiss.search(query_vector, top_k=5)
  → Retrieve chunk texts → inject into RAG prompt
```
