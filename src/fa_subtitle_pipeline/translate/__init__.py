"""Translation providers. `manual` and `none` are handled by the pipeline."""
from __future__ import annotations

from ..config import PipelineConfig
from .base import TranslationProvider
from .google import GoogleProvider
from .openai_provider import OpenAIProvider

_PROVIDERS: dict[str, type[TranslationProvider]] = {
    "google": GoogleProvider,
    "openai": OpenAIProvider,
}

ALL_PROVIDERS = ("manual", "google", "openai", "none")


def get_provider(cfg: PipelineConfig) -> TranslationProvider | None:
    """Return an automatic provider, or None for manual/none workflows."""
    name = cfg.translation_provider
    if name in ("manual", "none"):
        return None
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown translation provider {name!r}; choose one of {ALL_PROVIDERS}")
    return _PROVIDERS[name](cfg)


__all__ = ["get_provider", "ALL_PROVIDERS", "GoogleProvider", "OpenAIProvider"]
