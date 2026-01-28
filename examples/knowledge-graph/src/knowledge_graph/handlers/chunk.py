import hashlib
import logging
import mimetypes
from io import BytesIO

import logfire
from surrealdb import RecordID

from kaig.db import DB
from kaig.definitions import OriginalDocument

from ..conversion import ConvertersFactory
from ..conversion.definitions import (
    ChunkWithMetadata,
    DocumentStreamGeneric,
)
from ..definitions import Chunk, Tables
from ..utils import is_chunk_empty

logger = logging.getLogger(__name__)


def chunking_handler(db: DB, document: OriginalDocument) -> None:
    with logfire.span("Chunking {doc=}", doc=document.id):
        doc_stream = DocumentStreamGeneric(
            name=document.filename, stream=BytesIO(document.file)
        )

        embedding_model = (
            db.embedder.model_name if db.embedder else "text-embedding-3-small"
        )
        content_type = document.content_type
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(document.filename)
            if guessed:
                content_type = guessed

        converters = ConvertersFactory.get_converters(
            content_type, embedding_model
        )
        result = None
        last_error: Exception | None = None
        for converter in converters:
            try:
                result = converter.convert_and_chunk(doc_stream)
                logger.info("Using %s", converter.__class__.__name__)
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Converter %s failed for document %s: %s",
                    converter.__class__.__name__,
                    document.id,
                    e,
                )
        if result is None:
            logger.error(
                "Error chunking document %s: %s", document.id, last_error
            )
            if last_error:
                raise last_error
            raise RuntimeError("No converters available")

        for i, chunk in enumerate(result.chunks):
            chunk_text = (
                chunk.content if isinstance(chunk, ChunkWithMetadata) else chunk
            )
            logger.info(f"Processing chunk: {chunk_text[:60]}")
            if is_chunk_empty(chunk_text):
                continue

            hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
            chunk_id = RecordID(Tables.chunk.value, hash)

            # skip if it already exists
            if db.exists(chunk_id):
                continue

            # ------------------------------------------------------------------
            # -- Embed chunks and insert
            doc = Chunk(
                content=chunk_text,
                id=chunk_id,
                doc=document.id,
                index=i,
                metadata=chunk.metadata
                if isinstance(chunk, ChunkWithMetadata)
                else None,
            )

            try:
                _ = db.embed_and_insert(doc, table=Tables.chunk.value, id=hash)
            except Exception as e:
                logger.error(
                    f"Error embedding chunk {chunk_id} with len={len(doc.content)}: {type(e)} {e}"
                )
                raise e

        logger.info("Finished chunking!")
