# HANDOFF

Cross-machine / cross-session pickup notes for the RAG-fidelity project. Read this +
`docs/00_PLAN.md` and you're oriented. Treat **"pushed" as "saved"** — these environments
are ephemeral.

- **Repo / branch:** `methionine23/RAG_test` → `claude/rag-fidelity-genetic-summarization-6rak7j`
- **Latest commit at handoff:** `16cb347`
- **One-line goal:** measure the fidelity (faithfulness + completeness + provenance) of
  LLM/RAG summarization of clinical-genetics literature into mutation & clinical-case
  tables, and localize where fidelity is lost (sectioning vs retrieval vs generation).

## Locked decisions (don't re-litigate)

| Decision | Choice |
| --- | --- |
| Ground truth | **Reference-free** (source-derived fact inventory; the user's `HSPB1_ground_truth.tsv` is a P5 *calibration* set, not a dependency) |
| Fidelity dims | Faithfulness / Completeness / Provenance. **Normalization correctness is out of scope.** |
| Codebase | **Net-new standalone harness** (`genephen_eval/`); genePhen + Vertex are *future* pluggable backends |
| genePhen | **Deferred** — build the eval tool first |
| Use cases | UC1 HSPB1 (1–2 full PMC XML from Entrez, scaling to 30–50) · UC2 biochem PDF (pathway schema) · UC3 GTR XML (schema-chunked) |

## Current stage — what EXISTS and works

Real, tested, offline (stdlib only, no network/model):

- **`genephen_eval/` package** — end-to-end pipeline: ingest → chunk → retrieve →
  extract (mock backend) → S1/S2/S3 metrics → attribution → report.
  - `ingestion.py` PMC/PubMed XML parser + `naive_fixed` / `section_aware` chunkers
  - `inventory.py` source-derived fact inventory (reference-free recall standard)
  - `metrics/` sectioning (S1), retrieval (S2), generation (S3: tiered grounding,
    silver recall, provenance), consistency (SelfCheck), attribution (loss budget)
  - `backends/` `SummarizerBackend` interface + deterministic offline `MockRAGBackend`
  - `runner.py` temperature × K-sample sweep · `report.py` · `cli.py`
- **`tests/test_harness.py`** — 13 unit + e2e tests, all passing.
- **`prototype/`** — two illustrative demos + `fetch_entrez.py` + synthetic PMC-XML fixture.
- **`docs/00–05`** — plan, cited literature review, metric design, schemas/architecture,
  stage-evaluation method, baseline-notebook analysis + genePhen plugin path.

Verify in ~2 s:
```bash
python3 -m unittest discover -s tests
python3 -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --task case
python3 -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --chunker naive_fixed
```
With the mock backend, as temperature 0→1: faithfulness 1.0→0.91, hallucination
0.0→0.07, recall 0.88→0.49, self-consistency 1.0→0.27, and the attribution budget shifts
to GENERATION (0.12→0.52) while S1/S2 stay flat. `naive_fixed` adds a constant SECTIONING
loss (~0.06) that `section_aware` doesn't — the stage attribution working as intended.

## The plan (phases — see `docs/00_PLAN.md` §4)

P0 scoping/schemas ✅ · P1 UC1 ingestion (partial: XML parser + fixture ✅, real corpus
pending) · P2 backends (interface ✅, mock ✅, real pending) · P3 metric stack ✅ (model
tiers pending) · P4 experiment matrix (runner ✅, real backends pending) · P5 human
calibration (pending) · P6 UC2/UC3 (pending) · P7 analysis/report (renderer ✅).

## Planned next (pick up here, in order)

1. **First real backend** — wrap the baseline notebook's `DetailedReportAgent`
   (Vertex `gemini-2.0-flash`) as a `SummarizerBackend`; run against real Entrez XML.
   *Requires: GCP project/creds + NCBI egress → do this in the Vertex/GCP env, not the
   agent sandbox (NCBI + Vertex are both blocked here).* Use `prototype/fetch_entrez.py`
   (`db=pmc`) to pull 1–2 HSPB1 full-text XMLs first.
2. **Real faithfulness tier-2** — pass a MiniCheck/AlignScore `entailment_fn` into
   `cell_faithfulness` (replaces the lexical fallback for free-text fields).
3. **Real retriever** — swap `LexicalRetriever` for embeddings / the RAG engine's
   retriever behind the same `retrieve(query, chunks, k)` signature.
4. **UC3 GTR-XML + UC2 biochem-PDF ingesters** — same `Document` output contract;
   schema-specific chunking (docs/04 §7).
5. **P5 calibration** — load `HSPB1_ground_truth.tsv`; measure metric↔human agreement;
   audit inventory precision/recall to bound silver-recall bias.

## Concerns & gaps (read before trusting numbers)

- **Everything non-structural is currently a stub.** The backend is a mock, the retriever
  is lexical, faithfulness tier-2/3 is word-boundary grounding + lexical fallback (not
  NLI/LLM-judge). The *metrics/attribution/temperature machinery is real*; the model
  signals are not. Do not report mock-backend numbers as findings.
- **Reference-free recall is "silver."** The inventory can undercount (detector misses →
  optimistic recall) or overcount (spurious mentions → pessimistic). Must be audited (P5).
- **Long-document metric degradation** (arXiv 2511.07689): NLI/consistency metrics get
  noisy on long dense inputs. Mitigation baked in = cell↔span-level scoring, but re-check
  once real NLI is wired.
- **LLM-judge reliability** (tier-3, not yet built): use a *different* model family than
  the summarizer, fixed rubric, low judge temp, self-consistency, human calibration.
- **Baseline notebook bug to avoid inheriting:** it extracts from `Title` only and scores
  by exact match. Harness fixes both (logs the real input span; tiered grounding) — keep
  it that way (docs/05 §1).
- **Normalization at match time only.** We allow `p.S135F`↔`p.Ser135Phe` to *match*; the
  demo uses a 3-entry hand map. Real harness needs `hgvs`/Mutalyzer, but scoring
  normalization *correctness* stays out of scope.
- **PDF table parsing (UC2)** is the highest-risk ingestion; parser errors propagate into
  both extraction and the inventory. Use a strong table-aware parser; log parse quality.
- **genePhen plugin contract (future):** to score genePhen's *real* internals it must
  emit, per generation, `retrieved_context` spans + `chunk_boundaries` (docs/05 §3).
- **Access:** NCBI Entrez and Vertex are blocked inside the web agent sandbox (egress
  policy). Real-data / real-model runs must happen in the user's GCP environment.

## Continuity

- **This chat's memory** lives only on **claude.ai/code** (web session). A local Claude
  Code (VS Code) starts fresh and continues from the *code* — orient it with this file +
  `docs/00_PLAN.md`.
- Bring work across via git only; nothing lives in the container. `git status` clean +
  pushed before switching machines.
