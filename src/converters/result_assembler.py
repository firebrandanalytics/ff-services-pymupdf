"""Assembles extraction results into DocumentAnalysisResult format."""

from typing import Dict, List


class ResultAssembler:
    """Assembles paragraphs, tables, and images into a unified DocumentAnalysisResult."""

    def assemble(
        self,
        paragraphs: List[Dict],
        tables: List[Dict],
        images: List[Dict] = None,
        total_pages: int = 0,
    ) -> Dict:
        """
        Assemble extracted content into DocumentAnalysisResult format.

        This format matches the Azure Document Intelligence output used by doc-proc,
        ensuring consumers get identical structure regardless of backend.
        """
        images = images or []

        # Build content blocks for ordering
        content_blocks = []

        # Filter paragraphs that overlap with table bounding boxes
        filtered_paragraphs = self._filter_table_overlaps(paragraphs, tables)

        for para in filtered_paragraphs:
            bbox = para.get("bounding_box", {})
            content_blocks.append({
                "type": "paragraph",
                "page": para.get("page_number", 1),
                "y_position": bbox.get("y_min", 0),
                "content_id": para["id"],
            })

        for table in tables:
            bbox = table.get("bounding_box", {})
            content_blocks.append({
                "type": "table",
                "page": table.get("page_number", 1),
                "y_position": bbox.get("y_min", 0),
                "content_id": table["id"],
            })

        for img in images:
            bbox = img.get("bounding_box", {})
            content_blocks.append({
                "type": "image",
                "page": img.get("page_number", 1),
                "y_position": bbox.get("y_min", 0),
                "content_id": img["id"],
            })

        # Sort by page then y position
        content_blocks.sort(key=lambda b: (b["page"], b["y_position"]))

        # Build full text from filtered paragraphs
        full_text = "\n".join(p["content"] for p in filtered_paragraphs)

        return {
            "model_used": "pymupdf",
            "pages": total_pages,
            "paragraphs": filtered_paragraphs,
            "tables": tables,
            "images": images if images else [],
            "full_text": full_text,
            "content_blocks": content_blocks,
        }

    def _filter_table_overlaps(
        self, paragraphs: List[Dict], tables: List[Dict]
    ) -> List[Dict]:
        """Remove paragraphs that overlap with table bounding boxes."""
        if not tables:
            return paragraphs

        filtered = []
        for para in paragraphs:
            if not self._overlaps_any_table(para, tables):
                filtered.append(para)

        return filtered

    def _overlaps_any_table(self, para: Dict, tables: List[Dict]) -> bool:
        """Check if a paragraph bounding box overlaps with any table."""
        p_bbox = para.get("bounding_box")
        if not p_bbox:
            return False

        for table in tables:
            t_bbox = table.get("bounding_box")
            if not t_bbox:
                continue

            if para.get("page_number") != table.get("page_number"):
                continue

            # Check bounding box overlap
            overlap_x = max(0, min(p_bbox["x_max"], t_bbox["x_max"]) - max(p_bbox["x_min"], t_bbox["x_min"]))
            overlap_y = max(0, min(p_bbox["y_max"], t_bbox["y_max"]) - max(p_bbox["y_min"], t_bbox["y_min"]))

            if overlap_x > 0 and overlap_y > 0:
                return True

        return False
