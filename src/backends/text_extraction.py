"""Text extraction backend using PyMuPDF with font metadata."""

import json
import logging
from typing import Dict, Any, Tuple, List

import pymupdf

from .base import Backend
from ..converters.role_detector import RoleDetector
from ..converters.html_converter import HtmlConverter
from ..converters.result_assembler import ResultAssembler
from ..utils.page_filter import parse_page_range
from ..config import get_config

logger = logging.getLogger(__name__)


class TextExtractionBackend(Backend):
    """Backend for extracting structured content from PDFs using PyMuPDF."""

    SUPPORTED_OPERATIONS = ["extract"]

    def __init__(self):
        self.role_detector = RoleDetector()
        self.html_converter = HtmlConverter()
        self.assembler = ResultAssembler()

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

        output_format = options.get("output_format", "json")
        include_images = options.get("include_images", "false").lower() == "true"
        page_range = options.get("pages", "")

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception:
            raise ValueError("Invalid or corrupted PDF file")

        total_pages = len(doc)
        try:
            # Determine which pages to process
            if page_range:
                page_numbers = parse_page_range(page_range)
            else:
                page_numbers = list(range(1, total_pages + 1))

            # Extract content from all requested pages
            all_paragraphs = []
            all_tables = []
            all_content_blocks = []
            all_images = []
            para_counter = 0
            table_counter = 0
            img_counter = 0
            pages_processed = 0

            for page_num in page_numbers:
                if page_num < 1 or page_num > total_pages:
                    continue

                pages_processed += 1
                page = doc[page_num - 1]

                # Extract text blocks with font metadata
                paragraphs, para_counter = self._extract_paragraphs(
                    page, page_num, para_counter
                )

                # Extract tables
                tables, table_counter = self._extract_tables(
                    page, page_num, table_counter
                )

                # Extract images if requested
                if include_images:
                    images, img_counter = self._extract_images(
                        doc, page, page_num, img_counter
                    )
                    all_images.extend(images)

                all_paragraphs.extend(paragraphs)
                all_tables.extend(tables)
        finally:
            doc.close()

        # Detect semantic roles across all paragraphs
        config = get_config()
        self.role_detector.classify(
            all_paragraphs,
            title_threshold=config.extraction.title_font_size_threshold,
            heading_threshold=config.extraction.heading_font_size_threshold,
        )

        # Assemble the result
        result = self.assembler.assemble(
            paragraphs=all_paragraphs,
            tables=all_tables,
            images=all_images if include_images else [],
            total_pages=total_pages if not page_range else len(page_numbers),
        )

        # Format output
        if output_format == "html":
            output_data = self.html_converter.convert(result).encode("utf-8")
            fmt = "html"
        else:
            output_data = json.dumps(result, indent=2).encode("utf-8")
            fmt = "json"

        metadata = {
            "pages_processed": str(pages_processed),
            "total_paragraphs": str(len(all_paragraphs)),
            "total_tables": str(len(all_tables)),
            "model_used": "pymupdf",
        }

        return output_data, fmt, metadata

    def _extract_paragraphs(
        self, page, page_num: int, counter: int
    ) -> Tuple[List[Dict], int]:
        """Extract text blocks as paragraphs with font metadata."""
        paragraphs = []
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # type 0 = text block
                continue

            bbox = block["bbox"]
            block_text_parts = []
            font_sizes = []
            font_names = []
            is_bold = False

            for line in block.get("lines", []):
                line_text_parts = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    line_text_parts.append(span["text"])
                    font_sizes.append(span.get("size", 12.0))
                    font_names.append(span.get("font", ""))
                    flags = span.get("flags", 0)
                    if flags & 16:  # bold flag
                        is_bold = True

                if line_text_parts:
                    block_text_parts.append(" ".join(line_text_parts))

            content = "\n".join(block_text_parts).strip()
            if not content:
                continue

            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
            primary_font = max(set(font_names), key=font_names.count) if font_names else ""

            para_id = f"para-{counter}"
            counter += 1

            paragraphs.append({
                "id": para_id,
                "content": content,
                "role": None,  # Will be set by RoleDetector
                "page_number": page_num,
                "bounding_box": {
                    "x_min": bbox[0],
                    "y_min": bbox[1],
                    "x_max": bbox[2],
                    "y_max": bbox[3],
                },
                "font": {
                    "name": primary_font,
                    "size": round(avg_font_size, 1),
                    "bold": is_bold,
                },
            })

        return paragraphs, counter

    def _extract_tables(
        self, page, page_num: int, counter: int
    ) -> Tuple[List[Dict], int]:
        """Extract tables from a page."""
        tables = []

        try:
            found_tables = page.find_tables()
        except Exception as e:
            logger.warning(f"Table detection failed on page {page_num}: {e}")
            return tables, counter

        for table in found_tables.tables:
            table_id = f"table-{counter}"
            counter += 1

            bbox = table.bbox
            extracted = table.extract()

            if not extracted:
                continue

            # Build cells
            cells = []
            num_rows = len(extracted)
            num_cols = max(len(row) for row in extracted) if extracted else 0

            for row_idx, row in enumerate(extracted):
                for col_idx, cell_content in enumerate(row):
                    kind = "columnHeader" if row_idx == 0 else "content"
                    # PyMuPDF find_tables() does not expose merged cell spans,
                    # so row_span/column_span are always 1.
                    cells.append({
                        "row_index": row_idx,
                        "column_index": col_idx,
                        "row_span": 1,
                        "column_span": 1,
                        "content": str(cell_content) if cell_content is not None else "",
                        "kind": kind,
                    })

            tables.append({
                "id": table_id,
                "page_number": page_num,
                "rows": num_rows,
                "columns": num_cols,
                "cells": cells,
                "bounding_box": {
                    "x_min": bbox[0],
                    "y_min": bbox[1],
                    "x_max": bbox[2],
                    "y_max": bbox[3],
                },
            })

        return tables, counter

    def _extract_images(
        self, doc, page, page_num: int, counter: int
    ) -> Tuple[List[Dict], int]:
        """Extract embedded images from a page."""
        import base64
        images = []

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                img_data = doc.extract_image(xref)
                if not img_data:
                    continue

                img_id = f"img-{counter}"
                counter += 1

                # Get image bounding box
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    rect = img_rects[0]
                    bbox = {
                        "x_min": rect.x0,
                        "y_min": rect.y0,
                        "x_max": rect.x1,
                        "y_max": rect.y1,
                    }
                else:
                    bbox = {"x_min": 0, "y_min": 0, "x_max": 0, "y_max": 0}

                images.append({
                    "id": img_id,
                    "page_number": page_num,
                    "mime_type": f"image/{img_data['ext']}",
                    "data": base64.b64encode(img_data["image"]).decode("utf-8"),
                    "bounding_box": bbox,
                })

            except Exception as e:
                logger.warning(f"Failed to extract image xref={xref} on page {page_num}: {e}")

        return images, counter
