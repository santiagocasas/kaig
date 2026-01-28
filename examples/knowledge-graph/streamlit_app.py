import base64
import json
import logging
import mimetypes
import os
import threading
import unicodedata
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def _load_secrets() -> None:
    try:
        secrets = st.secrets.to_dict()
    except StreamlitSecretNotFoundError:
        return
    except Exception:
        return
    for key in (
        "BLABLADOR_API_KEY",
        "BLABLADOR_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    ):
        if key in secrets and not os.getenv(key):
            os.environ[key] = str(secrets[key])


_load_secrets()

if not os.getenv("OPENAI_API_KEY") and os.getenv("BLABLADOR_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["BLABLADOR_API_KEY"]
if not os.getenv("OPENAI_BASE_URL") and os.getenv("BLABLADOR_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = os.environ["BLABLADOR_BASE_URL"]
    os.environ["OPENAI_API_BASE"] = os.environ["BLABLADOR_BASE_URL"]

if not os.getenv("OPENAI_API_KEY"):
    st.error(
        "Missing BLABLADOR_API_KEY / OPENAI_API_KEY. "
        "Set it in `.streamlit/secrets.toml` or export it before running."
    )
    st.stop()

os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("KG_DB_URL", "ws://localhost:8000/rpc")
os.environ.setdefault("KG_SEARCH_THRESHOLD", "0.15")
os.environ.setdefault("KG_SEARCH_FALLBACK", "true")
os.environ.setdefault("KG_EMBEDDINGS_PROVIDER", "sentence-transformers")
os.environ.setdefault(
    "KG_LOCAL_EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
os.environ.setdefault("KG_DOCLING_TOKENIZER", "cl100k_base")
DEFAULT_MODEL = (
    "1 - GPT-OSS-120b - an open model released by OpenAI in August 2025"
)
MODEL_OPTIONS = [
    "0 - Ministral-3-14B-Instruct-2512 - The latest Ministral from Dec.2.2025",
    "1 - GPT-OSS-120b - an open model released by OpenAI in August 2025",
    "2 - Qwen3 235, a great model from Alibaba with a long context size",
    "7 - Qwen3-Coder-30B-A3B-Instruct - A code model from August 2025",
    "8 GLM-4.7-Flash",
    "8 GLM-4.7-Flash-AWQ-4bit",
    "999 NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
]
os.environ.setdefault("KG_LLM_MODEL", DEFAULT_MODEL)
os.environ.setdefault("KG_CHAT_MODEL", DEFAULT_MODEL)
os.environ.setdefault("KG_LLM_FALLBACK_MODELS", "alias-large,alias-huge")

from knowledge_graph.agent import Deps, db, get_agent, openai  # noqa: E402
from knowledge_graph.db import init_db  # noqa: E402
from knowledge_graph.definitions import Chunk  # noqa: E402
from knowledge_graph.handlers.chunk import chunking_handler  # noqa: E402
from knowledge_graph.handlers.inference import (  # noqa: E402
    inferrence_handler,
)


ROOT_DIR = Path(__file__).parent.parent.parent
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
INGESTION_LOG = LOG_DIR / "ingestion.log"
STATUS_FILE = LOG_DIR / "ingestion.status"
MAX_UPLOAD_MB = int(os.getenv("KG_MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
METADATA_PATH = Path(__file__).parent / "data" / "party_plan_metadata.json"
IMAGES_METADATA_PATH = ROOT_DIR / "images" / "metadata.json"
BLABLADOR_LOGO_PATH = ROOT_DIR / "logos" / "blablador-ng.svg"
APP_LOGO_PATH = ROOT_DIR / "logos" / "VotoCriterioIA.png"


def _write_status(status: str) -> None:
    STATUS_FILE.write_text(status, encoding="utf-8")


def _read_status() -> str:
    if STATUS_FILE.exists():
        return STATUS_FILE.read_text(encoding="utf-8").strip()
    return "idle"


def _ingestion_logger() -> logging.Logger:
    logger = logging.getLogger("knowledge_graph.streamlit_ingestion")
    logger.setLevel(logging.INFO)
    if not any(
        isinstance(handler, logging.FileHandler)
        and handler.baseFilename == str(INGESTION_LOG)
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(INGESTION_LOG)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def _tail_log(path: Path, lines: int = 20) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(data[-lines:])


def _render_svg(path: Path, width: int = 180) -> None:
    if not path.exists():
        return
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    st.markdown(
        (
            '<div style="margin: 0.25rem 0 0.5rem 0;">'
            f'<img src="data:image/svg+xml;base64,{encoded}" '
            f'width="{width}" />'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.lower()


def _normalize_words(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    stopwords = {
        "a",
        "al",
        "con",
        "de",
        "del",
        "el",
        "en",
        "la",
        "las",
        "los",
        "para",
        "por",
        "un",
        "una",
        "y",
    }
    words: list[str] = []
    for chunk in cleaned.replace("-", " ").split():
        token = "".join(ch for ch in chunk if ch.isalnum())
        if not token or token in stopwords or len(token) <= 2:
            continue
        if token:
            words.append(token)
    return words


def _strip_name_prefixes(name: str) -> str:
    normalized = _normalize_text(name).strip()
    prefixes = (
        "coalicion ",
        "partido ",
        "movimiento ",
        "frente ",
        "alianza ",
    )
    for prefix in prefixes:
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix).strip()
    return normalized


def _load_party_metadata() -> list[dict[str, str]]:
    if not METADATA_PATH.exists():
        return []
    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    parties = data.get("parties", [])
    if not isinstance(parties, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in parties:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        acronym = str(item.get("acronym", "")).strip()
        plan_url = str(item.get("plan_url", "")).strip()
        if name and acronym and plan_url:
            cleaned.append({"name": name, "acronym": acronym, "url": plan_url})
    return cleaned


def _load_party_images() -> list[dict[str, str]]:
    if not IMAGES_METADATA_PATH.exists():
        return []
    try:
        data = json.loads(IMAGES_METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    items: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        image_path = str(entry.get("image_path", "")).strip()
        if not image_path:
            continue
        text = " ".join(
            str(entry.get(key, "")) for key in ("alt", "title", "caption")
        ).strip()
        if not text:
            continue
        items.append(
            {
                "text": text,
                "path": image_path,
            }
        )
    return items


def _attach_party_images(
    parties: list[dict[str, str]], images: list[dict[str, str]]
) -> list[dict[str, str]]:
    if not parties or not images:
        return parties
    normalized_images = [
        {
            "text": _normalize_text(entry["text"]),
            "path": entry["path"],
        }
        for entry in images
    ]
    for party in parties:
        name_key = _normalize_text(party["name"])
        stripped_name = _strip_name_prefixes(party["name"])
        acronym = str(party.get("acronym", "")).strip()
        acronym_key = _normalize_text(acronym)
        acronym_words = [acronym_key] if acronym_key else []
        name_words = _normalize_words(name_key)
        stripped_words = _normalize_words(stripped_name)

        best_score = 0
        best_path: str | None = None
        for entry in normalized_images:
            text = entry["text"]
            score = 0
            if name_key and name_key in text:
                score = 4
            elif stripped_name and stripped_name in text:
                score = 3
            elif stripped_words and all(
                word in text for word in stripped_words
            ):
                score = 2
            elif name_words and all(word in text for word in name_words):
                score = 1
            if acronym_words and any(
                f" {word} " in f" {text} " for word in acronym_words
            ):
                score = max(score, 2)
            if score and "divisa" in text:
                score += 1
            if score > best_score:
                image_path = ROOT_DIR / entry["path"]
                if image_path.exists():
                    best_score = score
                    best_path = str(image_path)
        if best_path:
            party["image_path"] = best_path
    return parties


def _render_party_grid(items: list[dict[str, str]]) -> None:
    if not items:
        return
    st.subheader("Planes de gobierno 2026")
    st.caption("Accesos directos a los programas oficiales del TSE.")
    cols = 5
    for i in range(0, len(items), cols):
        row = st.columns(cols)
        for col, item in zip(row, items[i : i + cols], strict=False):
            with col:
                image_path = item.get("image_path")
                if image_path:
                    st.image(image_path, use_container_width=True)
                else:
                    _render_party_placeholder(item.get("acronym", ""))
                st.markdown(
                    "\n".join(
                        [
                            f"<strong>{item['name']}</strong>",
                            f'<a href="{item["url"]}" target="_blank">'
                            f"{item['acronym']} (ver plan)</a>",
                        ]
                    ),
                    unsafe_allow_html=True,
                )


def _render_party_placeholder(acronym: str) -> None:
    label = (acronym or "?").strip().upper()
    st.markdown(
        "\n".join(
            [
                '<div class="party-placeholder">',
                f'<div class="party-placeholder-acronym">{label}</div>',
                "</div>",
            ]
        ),
        unsafe_allow_html=True,
    )


def _run_ingestion(doc, db_name: str) -> None:
    logger = _ingestion_logger()
    _write_status("running")
    logger.info("Starting ingestion for %s", doc.filename)
    try:
        db_ingest = init_db(init_llm=True, db_name=db_name, init_indexes=False)
        chunking_handler(db_ingest, doc)

        stamp = "streamlit"
        db_ingest.sync_conn.query(
            "UPDATE $rec SET chunked = $hash",
            {"rec": doc.id, "hash": stamp},
        )

        chunks = db_ingest.query(
            """SELECT * FROM chunk
                WHERE doc = $doc
                AND concepts_inferred IS NONE
                ORDER BY index ASC
            """,
            {"doc": doc.id},
            dict,
        )
        for chunk_data in chunks:
            chunk = Chunk.model_validate(chunk_data)
            _ = inferrence_handler(db_ingest, chunk)
            db_ingest.sync_conn.query(
                "UPDATE $rec SET concepts_inferred = $hash",
                {"rec": chunk.id, "hash": stamp},
            )

        logger.info("Finished ingestion for %s", doc.filename)
        _write_status("finished")
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        _write_status(f"error: {exc}")


def _start_ingestion_thread(doc, db_name: str) -> None:
    thread = threading.Thread(
        target=_run_ingestion,
        args=(doc, db_name),
        daemon=True,
    )
    thread.start()


def _guess_content_type(filename: str, content_type: str | None) -> str:
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
        return "application/octet-stream"
    return content_type


def _is_port_open(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect(("127.0.0.1", port))
        except Exception:
            return False
    return True


def _status_line(label: str, ok: bool) -> str:
    icon = "✅" if ok else "❌"
    return f"{icon} {label}"


def _ingestion_badge(status: str) -> str:
    normalized = status.strip().lower()
    if normalized.startswith("running"):
        return "🟡 running"
    if normalized.startswith("finished"):
        return "✅ finished"
    if normalized.startswith("error"):
        return "❌ error"
    return "⚪ idle"


def _looks_english(text: str) -> bool:
    english_markers = (
        "based on the information",
        "i cannot",
        "i can't",
        "the retrieved documents",
        "you would need to",
        "to get accurate information",
        "the knowledge base",
        "in the context of",
        "the party",
        "government plan",
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
    lowered = text.lower()
    english_hits = sum(marker in lowered for marker in english_markers)
    spanish_hits = sum(marker in lowered for marker in spanish_markers)
    return english_hits >= 2 and spanish_hits < 2


st.set_page_config(page_title="Voto Criterio IA", layout="wide")

logo_col, title_col = st.columns([1, 6])
with logo_col:
    if APP_LOGO_PATH.exists():
        st.image(str(APP_LOGO_PATH), width=90)
with title_col:
    st.title("VotoCriterioIA")
    st.caption(
        "Análisis político asistido por IA a partir de documentos estructurados "
        "y fuentes públicas sobre el proceso electoral 2026 en Costa Rica"
    )

st.markdown(
    """
    <style>
    div[data-testid="stFileUploaderDropzone"] span {
        display: none !important;
    }
    div[data-testid="stFileUploaderDropzone"]::before {
        content: "Arrastra y suelta el archivo aqui o haz clic para seleccionarlo";
        display: block;
        color: #4b5563;
        font-size: 0.9rem;
        line-height: 1.4;
        padding: 0.4rem 0;
    }

    .party-placeholder {
        height: 110px;
        border-radius: 12px;
        background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 0.5rem;
    }

    .party-placeholder-acronym {
        font-weight: 700;
        letter-spacing: 0.08em;
        color: rgba(255, 255, 255, 0.92);
        font-size: 1.25rem;
        text-shadow: 0 1px 1px rgba(0, 0, 0, 0.25);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

party_metadata = _load_party_metadata()
party_images = _load_party_images()
party_metadata = _attach_party_images(party_metadata, party_images)
_render_party_grid(party_metadata)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "history" not in st.session_state:
    st.session_state.history = []
if "ingestion_running" not in st.session_state:
    st.session_state.ingestion_running = False
if "selected_model" not in st.session_state:
    st.session_state.selected_model = (
        DEFAULT_MODEL if DEFAULT_MODEL in MODEL_OPTIONS else MODEL_OPTIONS[0]
    )

current_status = _read_status()
if current_status.startswith("running"):
    st.session_state.ingestion_running = True
elif current_status:
    st.session_state.ingestion_running = False

if st.session_state.ingestion_running and hasattr(st, "autorefresh"):
    st.autorefresh(interval=3000, key="ingestion_refresh")

with st.sidebar:
    st.header("Status")
    st.caption(_status_line("SurrealDB (8000)", _is_port_open(8000)))
    st.caption(_status_line("Server (8080)", _is_port_open(8080)))
    st.caption(_status_line("Streamlit UI (8501)", _is_port_open(8501)))
    st.caption(f"DB name: {os.environ.get('DB_NAME', '')}")
    st.caption(f"Ingestion: {_ingestion_badge(current_status or 'idle')}")
    st.markdown("### Modelo")
    selected_index = MODEL_OPTIONS.index(st.session_state.selected_model)
    st.session_state.selected_model = st.selectbox(
        "Modelo Blablador",
        MODEL_OPTIONS,
        index=selected_index,
    )
    os.environ["KG_CHAT_MODEL"] = st.session_state.selected_model
    os.environ["KG_LLM_MODEL"] = st.session_state.selected_model
    st.caption(f"Modelo activo: {st.session_state.selected_model}")

    _render_svg(BLABLADOR_LOGO_PATH)
    st.caption(
        "Gracias a Blablador y a Helmholtz AI por el soporte con los modelos LLM"
    )

    st.divider()
    st.header("Subir documento")
    st.caption(
        "Sube un PDF o Markdown. Al confirmar, se guardara en la base y se "
        "iniciara la ingesta en segundo plano."
    )
    st.caption(f"Tamano maximo: {MAX_UPLOAD_MB} MB")

    uploaded = st.file_uploader(
        "Selecciona un PDF o Markdown",
        type=["pdf", "md", "markdown"],
        accept_multiple_files=False,
        disabled=st.session_state.ingestion_running,
    )
    if uploaded is not None and st.button(
        "Subir y procesar",
        disabled=st.session_state.ingestion_running,
    ):
        if uploaded.size and uploaded.size > MAX_UPLOAD_BYTES:
            st.error("File exceeds 50 MB limit.")
        else:
            content = uploaded.getvalue()
            content_type = _guess_content_type(uploaded.name, uploaded.type)
            doc, cached = db.store_original_document_from_bytes(
                uploaded.name,
                content_type,
                content,
            )
            if cached:
                st.info("Document already exists; ingestion will re-run.")
            st.session_state.ingestion_running = True
            _write_status("running")
            _start_ingestion_thread(doc, os.environ.get("DB_NAME", ""))
            st.success("Upload complete. Ingestion started.")

    st.divider()
    st.header("Ingestion logs")
    st.caption(f"Status: {current_status}")
    log_text = _tail_log(INGESTION_LOG, lines=20)
    if log_text:
        st.code(log_text, language="text")
    else:
        st.caption("No ingestion logs yet.")

    st.divider()
    if st.button("🗑️ Reset chat"):
        st.session_state.chat_messages = []
        st.session_state.history = []
        st.rerun()

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Pregunta sobre elecciones en Costa Rica")
if user_input:
    st.session_state.chat_messages.append(
        {"role": "user", "content": user_input}
    )
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                agent = get_agent(st.session_state.selected_model)
                result = agent.run_sync(
                    user_input,
                    deps=Deps(db, openai),
                    message_history=st.session_state.history,
                )
                response = result.output
                st.session_state.history = result.all_messages()
                if _looks_english(response):
                    retry = agent.run_sync(
                        user_input,
                        deps=Deps(db, openai),
                        message_history=st.session_state.history,
                        instructions="Responde solo en español.",
                    )
                    response = retry.output
                    st.session_state.history = retry.all_messages()
                if _looks_english(response):
                    response = "No tengo informacion en la base de conocimiento sobre ese tema."
            except Exception as exc:
                message = str(exc)
                if "Exceeded maximum retries" in message:
                    response = "No tengo informacion en la base de conocimiento sobre ese tema."
                else:
                    response = f"Error: {message}"
        st.markdown(response)

    st.session_state.chat_messages.append(
        {"role": "assistant", "content": response}
    )
