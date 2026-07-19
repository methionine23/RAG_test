"""genephen_eval — reference-free fidelity evaluation for LLM/RAG clinical-genetic
summarization.

Standalone evaluation harness (genePhen / Vertex plug in later as backends). Measures
fidelity at three stages — Sectioning/Chunking (S1), Retrieval (S2), Generation (S3) —
and attributes each lost/incorrect fact to the stage that caused it.

See docs/00–05 for the design.
"""
__version__ = "0.1.0"
