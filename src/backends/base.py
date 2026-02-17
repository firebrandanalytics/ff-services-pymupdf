"""Base backend interface for PDF processing operations."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple


class Backend(ABC):
    """Abstract base class for PDF processing backends."""

    @abstractmethod
    def supports(self, operation: str, format: str = "") -> bool:
        """
        Check if this backend can handle the specified operation.

        Args:
            operation: The operation name (e.g., "extract", "detect_text_layer")
            format: Optional format hint (e.g., "pdf")

        Returns:
            True if this backend supports the operation, False otherwise
        """
        pass

    @abstractmethod
    def process(
        self,
        data: bytes,
        operation: str,
        options: Dict[str, str]
    ) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Process PDF with the specified operation.

        Args:
            data: Raw PDF bytes
            operation: Operation to perform
            options: Operation-specific options

        Returns:
            Tuple of (output_data, format, metadata)
            - output_data: Processed output bytes
            - format: Output format (e.g., "json", "html")
            - metadata: Additional information about the processing

        Raises:
            ValueError: If operation is not supported or invalid options
            RuntimeError: If processing fails
        """
        pass
