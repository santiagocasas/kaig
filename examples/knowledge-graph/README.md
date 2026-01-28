# Knowledge Graph Example

This example builds a simple **knowledge graph** on top of **SurrealDB** from
uploaded documents, using a **data-flow pattern** to drive ingestion.

At a high level:

1. You upload a document to the FastAPI server (`/upload`).
2. The server stores it in SurrealDB as a `document` record.
3. A background ingestion worker runs *flows* that:
   - chunk documents into embedded `chunk` records
   - infer `concept` nodes from each chunk and create `MENTIONS_CONCEPT` edges
4. A separate chat agent can retrieve relevant chunks (vector + graph context)
   and answer using the ingested documents.

## Code layout

The package lives under `examples/knowledge-graph/src/knowledge_graph/`:

- `server.py`
  - FastAPI application and lifecycle management.
  - Starts the background ingestion loop on startup and stops it on shutdown.
  - Creates a `flow.Executor` bound to the SurrealDB connection.

- `ingestion.py`
  - Defines the ingestion pipeline by registering flow handlers with
    `@exe.flow(...)`.
  - Current flows:
    - `chunk`: processes `document` records that have not been chunked yet
    - `infer_concepts`: processes `chunk` records that have not had concepts
      inferred yet

- `flow/`
  - `executor.py`: generic runtime for the data-flow pattern (polls DB for work,
    executes handlers, applies backoff when idle).
  - `definitions.py`: `Flow` (Pydantic model) and shared types.

- `handlers/`
  - `upload.py`: receives a file and stores it as an original document in DB.
  - `chunk.py`: converts and chunks documents, embeds chunks, inserts them.
  - `inference.py`: uses the configured LLM to extract concepts and write
    `concept` nodes + `MENTIONS_CONCEPT` edges.

- `agent.py`
  - PydanticAI agent with a `retrieve` tool.
  - Runs SurrealQL from `surql/search_chunks.surql` to fetch relevant chunks and
    supplies them as context to the model.

- `surql/`
  - SurrealQL files for schema definition and retrieval queries.

## Data-flow pattern (flow/stamp) used here

This example uses a **database-driven data flow**:

- Each step (“flow”) queries a DB table for records that are eligible for
  processing.
- The step writes results back to the DB.
- The step marks completion by setting a *stamp field* on the record.

### Flow definition

Flows are registered via the `@exe.flow(table=..., stamp=..., dependencies=..., priority=...)`
decorator. Under the hood:

- The executor stores flow metadata in the `flow` table.
- Each handler is assigned a **stable hash** derived from its compiled code.
  This hash is written into the record’s stamp field after processing.

### Eligibility and dependencies

A record becomes a candidate when:

- its stamp field is `NONE` (meaning “not yet processed by this flow”), and
- all dependency fields (if any) are present (not `NONE`).

This makes the pipeline **restart-safe** and **incremental**:
if the server stops, it resumes based on DB state rather than in-memory state.

### Stamping and idempotency

Each handler must set its stamp field, e.g.:

- `document.chunked = <flow_hash>`
- `chunk.concepts_inferred = <flow_hash>`

This prevents reprocessing the same record and also makes changes traceable:
if you update a flow function, its hash changes and you can see which records
were processed by which version of the flow.

## Run:

### DB:

```bash
surreal start -u root -p root rocksdb:dbs/knowledge-graph
```

or use the helper script:

```bash
./scripts/run_surrealdb.sh
```

or `just knowledge-graph-db` from the repo base directory.

### LLM + embeddings (Blablador)

This example uses OpenAI-compatible APIs. For Blablador, set:

```bash
export OPENAI_API_KEY="$BLABLADOR_API_KEY"
export OPENAI_BASE_URL="${BLABLADOR_BASE_URL:-https://api.helmholtz-blablador.fz-juelich.de/v1/}"
```

Defaults are `alias-fast` for chat and local sentence-transformers embeddings.

Override chat model and fallbacks if needed:

```bash
export KG_LLM_MODEL=alias-fast
export KG_LLM_FALLBACK_MODELS=alias-large,alias-code
export KG_CHAT_MODEL=alias-fast
```

To use local embeddings explicitly:

```bash
export KG_EMBEDDINGS_PROVIDER=sentence-transformers
export KG_LOCAL_EMBEDDINGS_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

To try Blablador embeddings (may be unstable):

```bash
export KG_EMBEDDINGS_PROVIDER=openai
export KG_EMBEDDINGS_MODEL=alias-embeddings
```

### Server and ingestion worker

```bash
DB_NAME=test_db uv run --env-file .env -- fastapi run examples/knowledge-graph/src/knowledge_graph/server.py --port 8080
```

By default, ingestion is disabled so the server can start quickly. To enable
ingestion at startup:

```bash
export KG_ENABLE_INGESTION=true
```

Recommended flow for large uploads:

1) Upload documents.
2) Run ingestion separately.

To run ingestion separately (recommended for large backlogs):

```bash
./scripts/start_ingestion.sh
```

If you see WebSocket disconnects, switch to HTTP for the DB client:

```bash
export KG_DB_URL=http://localhost:8000
```

### PDF converter selection

By default, the ingestion flow prefers Docling with no fallback. You can
override the order with:

```bash
export KG_PDF_CONVERTER=docling
```

Other values: `kreuzberg` (prefer Kreuzberg), `auto` (try Kreuzberg first).

To enable fallback converters:

```bash
export KG_PDF_FALLBACK=true
```

Docling tokenizer configuration:

```bash
export KG_DOCLING_TOKENIZER=cl100k_base
```

### Markdown ingestion

You can upload `.md` files directly; they are chunked locally without PDF
conversion. The uploader also guesses content types by filename when missing.

If a file comes through as `application/octet-stream`, the ingestion pipeline
will attempt to guess the type from the filename before converting.

### Party plan metadata

The knowledge-graph example includes a metadata file for the 2026 party plan
PDFs. It is used to expand acronyms and to surface plan URLs in answers:

- `examples/knowledge-graph/data/party_plan_metadata.json`

or `just knowledge-graph test_db` from the repo base directory.

### Chat agent

```bash
DB_NAME=test_db uv run --env-file .env uvicorn knowledge_graph.agent:app --host 127.0.0.1 --port 7932
```

### Status check

```bash
./scripts/status_check.sh
```

This script now acts as a status checker and log tail helper. Logs are written
to `logs/server.log` and `logs/ui.log`.

### Quickstart scripts

Start SurrealDB:

```bash
./scripts/run_surrealdb.sh
```

Start server (foreground):

```bash
./scripts/start_server.sh
```

Start server in background:

```bash
./scripts/start_server.sh -b
```

Upload PDFs/Markdowns:

```bash
./scripts/upload_pdfs.sh /path/to/folder
```

Run ingestion (process backlog):

```bash
./scripts/start_ingestion.sh
```

Start UI:

```bash
source scripts/start_ui.sh
```

### Streamlit app (query-first)

Run locally (requires SurrealDB running):

```bash
export DB_NAME=test_db
streamlit run examples/knowledge-graph/streamlit_app.py
```

Uploads are limited to one PDF/Markdown at a time (default max 50 MB).
Ingestion runs in a background thread and writes logs to `logs/ingestion.log`.

The Streamlit UI can display party banner images using `images/metadata.json`.

Set the limit explicitly:

```bash
export KG_MAX_UPLOAD_MB=50
export STREAMLIT_SERVER_MAX_UPLOAD_SIZE=50
```

Docker (single container with SurrealDB inside):

```bash
docker build -f Dockerfile.streamlit -t kaig-streamlit .
docker run -p 8501:8501 \
  -e BLABLADOR_API_KEY=... \
  -e BLABLADOR_BASE_URL=https://api.helmholtz-blablador.fz-juelich.de/v1/ \
  kaig-streamlit
```

The build expects `dbs/knowledge-graph/` to be present in the build context.

SurrealDB retry settings (optional):

```bash
export KG_DB_RETRY_ATTEMPTS=3
export KG_DB_RETRY_DELAY=1.0
```

Check status:

```bash
./scripts/status_check.sh
```

Limit retrieval tool calls per question (default: 10):

```bash
export KG_MAX_RETRIEVE_CALLS=1
```

Tune search threshold and fallback:

```bash
export KG_SEARCH_THRESHOLD=0.15
export KG_SEARCH_FALLBACK=true
```

or `just knowledge-graph-agent test_db` from the repo base directory.

## SurrealQL queries:

**Visualise the graph:**

```surql
SELECT *,
    ->MENTIONS_CONCEPT->concept as concepts
FROM chunk;
```

**Flow status**

This will show how many records have been processed by and are pending for each "flow".

```surql
LET $flows = SELECT * FROM flow;

RETURN $flows.fold([], |$a, $flow| {
    LET $b = SELECT
            $flow.id as flow,
            type::field($flow.stamp) as flow_hash,
            count() as count,
            $flow.table as table
        FROM type::table($flow.table)
        GROUP BY flow_hash;
    RETURN $a.concat($b)
});
```

Output example:

```surql
[
	{
		count: 1,
		flow: flow:chunk,
		flow_hash: NONE,
		table: 'document'
	},
	{
		count: 2,
		flow: flow:chunk,
		flow_hash: 'bbb6fe4b55cce1b3c8af0e7713a33d75',
		table: 'document'
	},
	{
		count: 4,
		flow: flow:infer_concepts,
		flow_hash: NONE,
		table: 'chunk'
	},
	{
		count: 27,
		flow: flow:infer_concepts,
		flow_hash: '75f90c71db9aeb2cf6f871ba1f75828c',
		table: 'chunk'
	}
]
```

Different hashes mean the records have been processed by different versions of the flow function. This can happen if the flow function has been updated.
