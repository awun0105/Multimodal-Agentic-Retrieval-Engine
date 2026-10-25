"""Model providers for the per-video worker (ADR 0023).

Heavy libraries are imported when a provider is constructed, so the
model-independent helpers in each module run without torch or a GPU.
"""

__all__ = []
