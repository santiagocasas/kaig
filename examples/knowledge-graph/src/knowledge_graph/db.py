import logging
import os
from pathlib import Path

from kaig.db import DB
from kaig.definitions import VectorTableDefinition
from kaig.embeddings import Embedder
from kaig.llm import LLM

from .definitions import EdgeTypes, Tables

logger = logging.getLogger(__name__)


def init_db(init_llm: bool, db_name: str, init_indexes: bool = True) -> DB:
    tables = [Tables.document.value, Tables.concept.value, Tables.page.value]
    vector_tables = [
        VectorTableDefinition(Tables.chunk.value, "HNSW", "COSINE"),
        VectorTableDefinition(Tables.concept.value, "HNSW", "COSINE"),
    ]

    if init_llm:
        logger.info("Init LLM...")
        llm_model = os.getenv("KG_LLM_MODEL", "alias-fast")
        fallback_env = os.getenv("KG_LLM_FALLBACK_MODELS")
        if fallback_env:
            fallback_models = [
                x.strip() for x in fallback_env.split(",") if x.strip()
            ]
        elif llm_model != "alias-fast":
            fallback_models = ["alias-fast"]
        else:
            fallback_models = ["alias-large"]
        llm = LLM(
            provider="openai",
            model=llm_model,
            temperature=1,
            fallback_models=fallback_models,
        )
    else:
        logger.info("Init without LLM")
        llm = None
    embedder_provider = os.getenv(
        "KG_EMBEDDINGS_PROVIDER", "sentence-transformers"
    ).lower()
    embedder_model = os.getenv("KG_EMBEDDINGS_MODEL", "alias-embeddings")
    if embedder_provider in {"sentence-transformers", "local", "hf"}:
        embedder = Embedder(
            provider="sentence-transformers",
            model_name=os.getenv(
                "KG_LOCAL_EMBEDDINGS_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            vector_type="F32",
        )
    else:
        try:
            embedder = Embedder(
                provider="openai",
                model_name=embedder_model,
                vector_type="F32",
            )
        except Exception as exc:
            logger.warning(
                "Embeddings init failed (%s). Falling back to local embeddings.",
                exc,
            )
            embedder = Embedder(
                provider="sentence-transformers",
                model_name=os.getenv(
                    "KG_LOCAL_EMBEDDINGS_MODEL",
                    "sentence-transformers/all-MiniLM-L6-v2",
                ),
                vector_type="F32",
            )

    # -- DB connection
    url = os.getenv("KG_DB_URL", "ws://localhost:8000/rpc")
    db_user = "root"
    db_pass = "root"
    db_ns = "kaig"
    db_db = db_name
    db = DB(
        url,
        db_user,
        db_pass,
        db_ns,
        db_db,
        embedder,
        llm,
        tables=tables,
        original_docs_table="document",
        vector_tables=vector_tables,
        graph_relations=[EdgeTypes.MENTIONS_CONCEPT.value],
    )
    if llm:
        llm.set_analytics(db.insert_analytics_data)

    # Remove this if you don't want to clear all your tables on every run
    # db.clear()

    surqls: list[str] = []
    for filename in ["schema.surql"]:
        file_path = Path(__file__).parent.parent.parent / "surql" / filename
        with open(file_path, "r") as file:
            surqls.append(file.read())

    for surql in surqls:
        _ = db.sync_conn.query(surql)
    db.init_db(force=init_indexes)

    return db
