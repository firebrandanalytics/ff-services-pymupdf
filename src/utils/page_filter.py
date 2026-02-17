"""Utility functions for page selection and filtering."""

from typing import List


def parse_page_range(page_range: str) -> List[int]:
    """
    Parse page range string into list of page numbers.

    Args:
        page_range: Page range string (e.g., "1,3,5-10")
                   Pages are 1-indexed.

    Returns:
        List of page numbers (1-indexed)
    """
    pages = set()

    for part in page_range.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-', 1)
            start = int(start.strip())
            end = int(end.strip())
            if start > end:
                raise ValueError(f"Invalid page range: {part} (start > end)")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))

    return sorted(list(pages))
