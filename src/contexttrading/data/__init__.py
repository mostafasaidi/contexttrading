"""Data layer (Phase 8+): provider adapters, ingestion, validation, storage.

Produces validated, UTC-normalized ``CandleSeries`` instances. See
docs/architecture/layers.md §1.
"""

from contexttrading.data.store import PAYLOAD_MODELS, ResultStore, hash_series

__all__ = ["PAYLOAD_MODELS", "ResultStore", "hash_series"]
