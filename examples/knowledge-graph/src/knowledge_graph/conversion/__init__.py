import logging
import os

from .providers import BaseConverter
from .providers.docling import DoclingConverter
from .providers.kreuzberg_converter import KreuzbergConverter
from .providers.markdown_converter import MarkdownConverter

logger = logging.getLogger(__name__)


class ConvertersFactory:
    @staticmethod
    def get_converters(
        content_type: str, embedding_model: str
    ) -> list[BaseConverter]:
        preferred = os.getenv("KG_PDF_CONVERTER", "docling").lower()
        fallback_enabled = os.getenv("KG_PDF_FALLBACK", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        converters: list[BaseConverter] = []

        def add_docling() -> None:
            if DoclingConverter.supports_content_type(content_type):
                converters.append(DoclingConverter(embedding_model))

        def add_kreuzberg() -> None:
            if KreuzbergConverter.supports_content_type(content_type):
                converters.append(KreuzbergConverter(content_type))

        def add_markdown() -> None:
            if MarkdownConverter.supports_content_type(content_type):
                converters.append(MarkdownConverter())

        add_markdown()
        if converters:
            return converters

        match preferred:
            case "docling":
                add_docling()
                if fallback_enabled:
                    add_kreuzberg()
            case "kreuzberg":
                add_kreuzberg()
                if fallback_enabled:
                    add_docling()
            case "auto":
                add_docling()
                if fallback_enabled:
                    add_kreuzberg()
            case _:
                add_docling()
                if fallback_enabled:
                    add_kreuzberg()

        if not converters:
            raise ValueError(f"Unsupported content type: {content_type}")

        return converters
