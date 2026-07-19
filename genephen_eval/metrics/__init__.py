"""Fidelity metrics, organized by RAG stage (docs/04).

  sectioning  — S1: structure preservation of the chunker
  retrieval   — S2: whether evidence reaches the generator
  generation  — S3: faithfulness / completeness / provenance of the produced table
  consistency — SelfCheckGPT-style stability across samples/temperatures
  attribution — assign each lost/incorrect fact to the stage that caused it
"""
