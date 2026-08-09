# AI Assistant - AI Assistant berbasis web (FastAPI)

Backend AI assistant modular: chat streaming, orchestration intent, RAG, tools/agents,
guardrail, dan deep analysis. Konfigurasi via YAML + `.env`, prompt via Jinja2 template.

## Arsitektur

```
Frontend (HTML/CSS/JS, SSE streaming)
        │  HTTP / SSE
        ▼
FastAPI app (app/)
 ├─ api/routes     → auth, conversations, chat, documents
 ├─ services       → auth, conversation, chat, audit, observability
 ├─ orchestrator   → intent router + mode runner (simple/rag/sql/deep)
 ├─ rag            → ingestion, chunking, embeddings, vectorstore (adapter)
 ├─ agents         → tool registry, deep-analysis planner/executor/evaluator/synthesizer
 ├─ guardrails     → pre-LLM & post-LLM checks, masking
 ├─ llm            → provider abstraction (OpenAI-compatible), prompt manager (Jinja2)
 └─ core           → config (env+YAML), logging, security helpers
```

### Alur data end-to-end

```
User Input
   -> Guardrail (pre): prompt injection / topic / permission
   -> Intent Router:       -> simple | knowledge(rag) | data_sql(sql) | analysis(deep)
   -> Orchestrator:  build pipeline utk mode tsb
        simple:  LLM langsung
        rag:     retrieve(top_k) -> inject context -> LLM
        sql:     LLM-to-SQL -> validasi -> jalankan (read-only) -> summary
        deep:    Planner -> Executor(tasks) -> Evaluator -> Synthesizer
   -> Guardrail (post): output validation & sensitive masking
   -> SSE streaming ke frontend  (alur saat ini: streaming per kuota)
   -> Simpan conversation/message + audit log
   -> Helper.validate -> Final Answer
```

### Folder structure

```
ai-assistant/
├── app/                  # source (package `app`)
│   ├── main.py           # app factory + middleware
│   ├── core/             # config, logging, security
│   ├── db/               # SQLAlchemy engine/session/models
│   ├── api/              # FastAPI routes + deps + schemas
│   ├── services/         # business logic layer
│   ├── llm/              # LLM client, prompts (Jinja2), streaming
│   ├── orchestrator/     # router + mode runners
│   ├── rag/              # RAG pipeline + vectorstore adapter
│   ├── guardrails/       # pre/post check
│   ├── agents/           # base agent, registry, deep-analysis, tools
│   └── utils/
├── config/               # YAML: settings.yaml, agents.yaml (nanti: business.yaml, sql/)
├── prompts/              # *.j2 (system, router, planner, evaluator, synthesis, guardrail, rag)
├── data/                 # sqlite db, vector store, uploads (gitignored)
├── tests/                # pytest
└── .env / .env.example   # secrets/doc-config
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
cp .env.example .env          # lalu isi LLM_API_KEY dll
.venv/bin/uvicorn app.main:app --reload
```

Uji cepat: `curl http://127.0.0.1:8000/health`

Jalankan test: `.venv/bin/python -m pytest tests/ -v`

## Fase pembangunan

1. Project skeleton + architecture ✅
2. Authentication & conversation (db, JWT)
3. Basic chat LLM (streaming SSE)
4. Orchestrator & routing
5. RAG
6. Tools/agents
7. Deep analysis
8. Guardrail & security
9. Testing & debugging

## Design notes

- **Config**: rahasia hanya di `.env`; nilai non-rahasia di `config/*.yaml`. `app/core/config.py`
  menggabungkan keduanya menjadi satu objek `AppConfig`.
- **Prompt**: semua prompt adalah template Jinja2 di `prompts/`, dikelola oleh `app/llm/prompts.py`.
- **Vector DB / embedding**: interface adapter di `app/rag/vectorstores/` (default Qdrant in-memory),
  penggantian provider cukup menambah adapter baru, tanpa mengubah pipeline RAG.
- **Tools**: tidak pernah dijalankan bebas; wajib lewat permission check + validation
  (lihat `guardrails` dan `agents`).
- **Observability**: log terstruktur (JSON) dengan `request_id`, redaksi otomatis field sensitif;
  API key tidak pernah ditulis ke log/audit.