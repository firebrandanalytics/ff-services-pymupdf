"""Configuration management for the PyMuPDF processing service."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionConfig:
    """Configuration for PDF extraction."""
    title_font_size_threshold: float = field(
        default_factory=lambda: float(os.environ.get("TITLE_FONT_SIZE_THRESHOLD", "18"))
    )
    heading_font_size_threshold: float = field(
        default_factory=lambda: float(os.environ.get("HEADING_FONT_SIZE_THRESHOLD", "14"))
    )
    text_layer_char_threshold: int = field(
        default_factory=lambda: int(os.environ.get("TEXT_LAYER_CHAR_THRESHOLD", "50"))
    )
    max_file_size_mb: int = field(
        default_factory=lambda: int(os.environ.get("MAX_FILE_SIZE_MB", "100"))
    )


@dataclass
class ServerConfig:
    """Configuration for HTTP server."""
    host: str = field(
        default_factory=lambda: os.environ.get("HTTP_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.environ.get("HTTP_PORT", "8089"))
    )


@dataclass
class Config:
    """Main configuration container."""
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Force reload of configuration from environment."""
    global _config
    _config = Config()
    return _config
