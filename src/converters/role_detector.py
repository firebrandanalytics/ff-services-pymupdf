"""Semantic role detection from font heuristics."""

import logging
from collections import Counter
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RoleDetector:
    """Classifies paragraphs as title, sectionHeading, or body text using font characteristics."""

    def classify(
        self,
        paragraphs: List[Dict],
        title_threshold: float = 18.0,
        heading_threshold: float = 14.0,
    ) -> None:
        """
        Classify paragraph roles in-place based on font heuristics.

        Uses a two-pass approach:
        1. Determine the body font size (most common size)
        2. Classify based on relative size and absolute thresholds

        Args:
            paragraphs: List of paragraph dicts (modified in-place)
            title_threshold: Font size above which text is classified as title
            heading_threshold: Font size above which text is classified as heading
        """
        if not paragraphs:
            return

        # Determine body font size from frequency distribution
        body_size = self._detect_body_font_size(paragraphs)
        logger.debug(f"Detected body font size: {body_size}")

        for para in paragraphs:
            font = para.get("font", {})
            font_size = font.get("size", 12.0)
            is_bold = font.get("bold", False)

            role = self._classify_single(
                font_size=font_size,
                is_bold=is_bold,
                body_size=body_size,
                title_threshold=title_threshold,
                heading_threshold=heading_threshold,
            )
            para["role"] = role

    def _detect_body_font_size(self, paragraphs: List[Dict]) -> float:
        """Find the most common font size (assumed to be body text)."""
        sizes = []
        for para in paragraphs:
            font = para.get("font", {})
            size = font.get("size", 12.0)
            # Weight by content length — longer paragraphs are more likely body text
            weight = min(len(para.get("content", "")), 200)
            sizes.extend([round(size, 1)] * weight)

        if not sizes:
            return 12.0

        counter = Counter(sizes)
        return counter.most_common(1)[0][0]

    def _classify_single(
        self,
        font_size: float,
        is_bold: bool,
        body_size: float,
        title_threshold: float,
        heading_threshold: float,
    ) -> Optional[str]:
        """Classify a single paragraph based on font characteristics."""
        # Title: large font, typically >= title_threshold or significantly larger than body
        if font_size >= title_threshold:
            return "title"

        if font_size >= body_size * 1.5 and is_bold:
            return "title"

        # Section heading: medium-large font or bold + larger than body
        if font_size >= heading_threshold:
            return "sectionHeading"

        if is_bold and font_size > body_size * 1.1:
            return "sectionHeading"

        # Body text
        return None
