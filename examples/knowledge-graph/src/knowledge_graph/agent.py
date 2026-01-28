import json
import json
import logging
import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import logfire
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from surrealdb import Value

from kaig.db import DB
from kaig.db.utils import query

from .db import init_db

logger = logging.getLogger(__name__)
stdout = logging.StreamHandler(stream=sys.stdout)
stdout.setLevel(logging.DEBUG)
logger.setLevel(logging.DEBUG)
logger.addHandler(stdout)


base_dir = Path(__file__).parent.parent.parent
surql_dir = base_dir / "surql"
metadata_path = base_dir / "data" / "party_plan_metadata.json"
with open(surql_dir / "search_chunks.surql", "r") as file:
    search_surql = file.read()
with open(surql_dir / "search_chunks_text.surql", "r") as file:
    search_text_surql = file.read()


@dataclass
class Deps:
    db: DB
    openai: AsyncOpenAI


@dataclass
class ResultChunk:
    id: str
    score: float
    chunk_index: int
    content: str


@dataclass
class DocHandle:
    id: str
    filename: str
    content_type: str


@dataclass
class SearchResult:
    doc: DocHandle
    best_chunk_score: float
    chunks: list[ResultChunk]
    summary: str


chat_model = (
    os.getenv("KG_CHAT_MODEL") or os.getenv("KG_LLM_MODEL") or "alias-fast"
)
max_retrieve_calls = int(os.getenv("KG_MAX_RETRIEVE_CALLS", "10"))
search_threshold = float(os.getenv("KG_SEARCH_THRESHOLD", "0.15"))
fallback_enabled = os.getenv("KG_SEARCH_FALLBACK", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.lower()


def _load_party_metadata() -> list[dict[str, str]]:
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        logger.warning("Invalid party metadata JSON")
        return []
    parties = data.get("parties", [])
    if not isinstance(parties, list):
        return []
    return [
        {
            "name": str(item.get("name", "")),
            "acronym": str(item.get("acronym", "")),
            "plan_url": str(item.get("plan_url", "")),
        }
        for item in parties
        if isinstance(item, dict)
    ]


party_metadata = _load_party_metadata()
acronym_map = {
    _normalize_text(item["acronym"]): item for item in party_metadata
}
name_map = {_normalize_text(item["name"]): item for item in party_metadata}

agent_instructions = f"""
    Responde siempre en español.
    No incluyas frases en inglés ni traducciones.
    Responde solo sobre la politica electoral de Costa Rica, incluyendo partidos
    politicos, elecciones, instituciones electorales y temas relacionados.
    Si la pregunta no es sobre eso, responde que solo puedes responder sobre
    elecciones y politica de Costa Rica.

    Usa la metadata de planes de gobierno 2026 para interpretar acronimos y
    nombres de partidos. Puedes mencionar el enlace al plan cuando sea relevante.

    Base tus respuestas en la base de conocimiento y menciona el nombre del
    documento en la respuesta. No inventes informacion.
    Si no hay informacion relevante, responde: "No tengo informacion en la base
    de conocimiento sobre ese tema.".
    No hagas preguntas de seguimiento.

    Llama a la herramienta retrieve como maximo {max_retrieve_calls} veces por
    pregunta. Si retrieve devuelve NO_RESULTS, responde que la base de
    conocimiento no tiene informacion relevante.
"""


def build_agent(model_name: str) -> Agent[Deps, str]:
    agent = Agent(
        f"openai:{model_name}",
        deps_type=Deps,
        instructions=agent_instructions,
        output_retries=2,
    )

    @agent.output_validator
    def ensure_spanish_response(output: str) -> str:
        markers = (
            "based on the information",
            "i cannot",
            "i can't",
            "the retrieved documents",
            "you would need to",
            "to get accurate information",
            "the knowledge base",
            "in the context of",
            "however,",
            "i do not have",
        )
        spanish_markers = (
            " el ",
            " la ",
            " de ",
            " que ",
            " para ",
            " sobre ",
            " partido ",
            " elecciones ",
            " costa ",
            " rica ",
            " gobierno ",
        )
        lowered = output.lower()
        english_hit = any(marker in lowered for marker in markers)
        spanish_score = sum(marker in lowered for marker in spanish_markers)
        if english_hit and spanish_score < 3:
            raise ModelRetry(
                "Responde solo en español y sin frases en inglés. "
                "Si no hay datos, usa la frase indicada."
            )
        return output

    @agent.tool
    async def retrieve(context: RunContext[Deps], search_query: str) -> str:
        """Retrieve documents from the user's knowledge base based on a search query.

        Args:
            context: The call context.
            search_query: The search query.
        """
        db = context.deps.db

        if context.usage.tool_calls >= max_retrieve_calls:
            logger.warning("Retrieve call limit reached")
            return "NO_RESULTS"

        query_text = search_query.strip()
        normalized_query = _normalize_text(query_text)
        matched_items: list[dict[str, str]] = []

        for key, item in acronym_map.items():
            if key and key in normalized_query:
                matched_items.append(item)
        for key, item in name_map.items():
            if key and key in normalized_query and item not in matched_items:
                matched_items.append(item)

        if matched_items:
            expansions = " ".join(
                item["name"] for item in matched_items if item["name"]
            )
            if (
                expansions
                and _normalize_text(expansions) not in normalized_query
            ):
                query_text = f"{query_text} {expansions}"

        with logfire.span(
            "vector+graph search for {search_query=}",
            search_query=search_query,
        ):
            if db.embedder is None:
                raise ValueError("Embedder is not configured")

            embedding = db.embedder.embed(query_text)
            results = query(
                db.sync_conn,
                search_surql,
                {
                    "embedding": cast(Value, embedding),
                    "threshold": search_threshold,
                },
                SearchResult,
            )

            if not results and fallback_enabled:
                results = query(
                    db.sync_conn,
                    search_text_surql,
                    {"query": query_text},
                    SearchResult,
                )

        metadata_lines = []
        for item in matched_items:
            name = item.get("name")
            acronym = item.get("acronym")
            plan_url = item.get("plan_url")
            if name and acronym and plan_url:
                metadata_lines.append(f"- {name} ({acronym}): {plan_url}")

        metadata_text = ""
        if metadata_lines:
            metadata_text = (
                "# Metadata: planes de gobierno 2026\n"
                + "\n".join(metadata_lines)
                + "\n\n"
            )

        if not results:
            return (
                f"{metadata_text}NO_RESULTS" if metadata_text else "NO_RESULTS"
            )

        results = "\n\n".join(
            f"# Document name: {x.doc.filename}\n"
            f"{'\n\n'.join(str(y.content) for y in x.chunks)}\n"
            for x in results
        )
        # logger.debug("Retrieved data: %s", results)
        return f"{metadata_text}{results}" if metadata_text else results

    return agent


_agent_cache: dict[str, Agent[Deps, str]] = {}


def get_agent(model_name: str) -> Agent[Deps, str]:
    if model_name not in _agent_cache:
        _agent_cache[model_name] = build_agent(model_name)
    return _agent_cache[model_name]


def _get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or os.getenv("BLABLADOR_API_KEY")


def _get_openai_base_url() -> str | None:
    base_url = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("BLABLADOR_BASE_URL")
    )
    if not base_url:
        return None
    return base_url.rstrip("/") + "/"


api_key = _get_openai_api_key()
if not api_key:
    raise ValueError(
        "OPENAI_API_KEY or BLABLADOR_API_KEY environment variable is not set"
    )
base_url = _get_openai_base_url()
if base_url:
    openai = AsyncOpenAI(api_key=api_key, base_url=base_url)
else:
    openai = AsyncOpenAI(api_key=api_key)

_ = logfire.configure(send_to_logfire="if-token-present")
logfire.instrument_pydantic_ai()
logfire.instrument_surrealdb()
_ = logfire.instrument_openai(openai)

db_name = os.environ.get("DB_NAME")
if not db_name:
    raise ValueError("DB_NAME environment variable is not set")

db = init_db(init_llm=False, db_name=db_name, init_indexes=False)

# Agent chat UI
agent = get_agent(chat_model)
app = agent.to_web(deps=Deps(db, openai))
