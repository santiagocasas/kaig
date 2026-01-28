import os
import os
from pathlib import Path
from typing import override

from knowledge_graph.conversion.definitions import (
    ChunkDocumentResult,
    DocumentStreamGeneric,
)
from knowledge_graph.utils import safe_path

from ..providers import BaseConverter


def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if max_chars <= 0:
        return [cleaned]
    if overlap < 0:
        overlap = 0
    step = max_chars - overlap if max_chars > overlap else max_chars
    chunks = []
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start : start + max_chars]
        if chunk:
            chunks.append(chunk)
    return chunks


class MarkdownConverter(BaseConverter):
    def __init__(self) -> None:
        self._chunk_size = int(os.getenv("KG_TEXT_CHUNK_SIZE", "1000"))
        self._overlap = int(os.getenv("KG_TEXT_CHUNK_OVERLAP", "100"))

    @staticmethod
    def supported() -> list[str]:
        return ["text/markdown", "text/plain"]

    @override
    def convert_and_chunk(
        self, source: DocumentStreamGeneric | Path
    ) -> ChunkDocumentResult:
        if isinstance(source, Path):
            source = safe_path(Path("/"), source)
            text = source.read_text(encoding="utf-8", errors="ignore")
            name = source.name
        else:
            text = source.stream.getvalue().decode("utf-8", errors="ignore")
            name = source.name
        chunks = _chunk_text(text, self._chunk_size, self._overlap)
        return ChunkDocumentResult(filename=name, chunks=chunks)

    @override
    async def convert_and_chunk_async(
        self, source: DocumentStreamGeneric | Path
    ) -> ChunkDocumentResult:
        return self.convert_and_chunk(source)
