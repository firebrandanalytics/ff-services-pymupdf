"""Text layer detection backend using PyMuPDF."""

import json
import logging
from typing import Dict, Any, Tuple

import pymupdf

from .base import Backend
from ..config import get_config

logger = logging.getLogger(__name__)


class TextLayerDetectionBackend(Backend):
    """Backend for detecting which pages have extractable text layers."""

    SUPPORTED_OPERATIONS = ["detect_text_layer"]

    def supports(self, operation: str, format: str = "") -> bool:
        return operation in self.SUPPORTED_OPERATIONS

    def process(
        self,
        data: bytes,
        operation: str,
        options: Dict[str, str]
    ) -> Tuple[bytes, str, Dict[str, Any]]:
        if not self.supports(operation):
            raise ValueError(f"Operation '{operation}' not supported")

        config = get_config()
        threshold = int(options.get(
            "char_threshold",
            str(config.extraction.text_layer_char_threshold)
        ))

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception:
            raise ValueError("Invalid or corrupted PDF file")

        try:
            pages = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                char_count = len(text.strip())

                pages.append({
                    "page": page_num + 1,
                    "has_text_layer": char_count >= threshold,
                    "char_count": char_count,
                })
        finally:
            doc.close()

        result = {
            "total_pages": len(pages),
            "pages": pages,
        }

        output_data = json.dumps(result, indent=2).encode("utf-8")
        metadata = {
            "total_pages": str(len(pages)),
            "pages_with_text": str(sum(1 for p in pages if p["has_text_layer"])),
            "threshold": str(threshold),
        }

        return output_data, "json", metadata
