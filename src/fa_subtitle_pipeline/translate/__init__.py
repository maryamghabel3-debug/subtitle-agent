"""Translation providers. `manual` and `none` are handled by the pipeline."""
from __future__ import annotations

import os

from ..config import PipelineConfig
from .base import TranslationProvider
from .google import GoogleProvider
from .openai_provider import OpenAIProvider

_PROVIDERS: dict[str, type[TranslationProvider]] = {
    "google": GoogleProvider,
    "openai": OpenAIProvider,
}

ALL_PROVIDERS = ("manual", "auto", "google", "openai", "none")


def get_provider(cfg: PipelineConfig) -> TranslationProvider | None:
    """Return an automatic provider, or None for manual/none workflows.

    `auto` means: use the OpenAI-compatible API when its key environment
    variable is set; until then behave like `manual` (pause for a human or
    an AI chat to translate). This is the mode the GitHub workflows use, so
    the day a key is added as a secret, translation becomes automatic with
    no other change.
    """
    name = cfg.translation_provider
    if name in ("manual", "none"):
        return None
    if name == "auto":
        if os.environ.get(cfg.translation_api_key_env):
            return OpenAIProvider(cfg)
        return None
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown translation provider {name!r}; choose one of {ALL_PROVIDERS}")
    return _PROVIDERS[name](cfg)


__all__ = ["get_provider", "ALL_PROVIDERS", "GoogleProvider", "OpenAIProvider"]
