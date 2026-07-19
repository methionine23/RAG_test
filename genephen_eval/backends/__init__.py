"""Summarizer backends. genePhen and Vertex RAG Engine attach here in a later phase
(docs/05 §3); today only the deterministic offline MockRAGBackend is wired."""
from .base import SummarizerBackend
from .mock import MockRAGBackend

__all__ = ["SummarizerBackend", "MockRAGBackend"]
