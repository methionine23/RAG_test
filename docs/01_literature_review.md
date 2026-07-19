# 01 — Literature Review: Metrics & Benchmarks

Synthesis of a multi-source, adversarially-verified literature sweep (2023–2025 arXiv +
ACL/EMNLP/TACL/SIGIR/Bioinformatics/MLHC). Each entry notes **what it measures**, its
**key limitation**, and whether it is **reference-free** (RF) or needs a gold reference
(RB). ★ = adopted in our design (see `docs/02`).

> Headline: the field has consolidated on **reference-free factual-consistency** metrics
> (NLI-based and QA-based), moving away from overlap metrics (ROUGE/BERTScore) as
> faithfulness proxies. For RAG, reference-free **LLM-as-judge** frameworks dominate.
> Two purpose-built **clinical-genetics** benchmarks now exist. But short-form
> consistency metrics degrade on **long, information-dense** documents — exactly our
> setting — which shapes our cell-level scoring choice.

## A. Faithfulness / factual-consistency metrics

| Metric | Measures | RF/RB | Limitation | Cite |
| --- | --- | --- | --- | --- |
| ★ **AlignScore** | Text-to-text information alignment on a (context, claim) pair; unified NLI/QA alignment model | RF | Degrades on long/dense docs; author-reported leaderboard | ACL 2023 (Zha et al.); github.com/yuh-zha/AlignScore |
| ★ **SummaC** (ZS / Conv) | Sentence-level NLI entailment matrix between document and summary sentences | RF | SummaC-**ZS** flagged least reliable on long docs | TACL 2022 (Laban et al.) |
| ★ **MiniCheck / UniEval** | Efficient fact-checking of claims vs grounding text | RF | More robust than AlignScore/SummaC-ZS on long docs but still struggle with logical negation | via stress-test arXiv 2511.07689 |
| **FactCC** | Weakly-supervised classifier for doc↔summary consistency | RF | Older; weaker than NLI/alignment SOTA | (survey) |
| **QuestEval / QAG** | Generate questions, compare answers from source vs summary | RF | QG/QA error compounding; slower | (survey) |
| **Atomic-facts entailment (RAG)** | Decompose source & summary into atomic facts, LLM cross-compares into error categories, NB classifier predicts factual | RF | Needs an LLM + a trained classifier layer | arXiv 2408.15171 (Kriman 2024) |
| ROUGE / BERTScore | n-gram / embedding overlap with a reference | RB | **Overlap ≠ faithfulness**; not a fidelity metric — use only descriptively | (survey) |

**Survey anchor:** *Trust but Verify* (RANLP 2025) reviews 40+ faithfulness-evaluation
studies (2020–2025) and taxonomizes them into human, QA-based, NLI-based, graph-based,
and LLM-based families — our reference map for the space. (aclanthology.org/2025.ranlp-1.74)

**Critical caveat we design around:** *Stress Testing Factual Consistency Metrics for
Long-Document Summarization* (arXiv 2511.07689, 2025) shows BARTScore, SummaC-Conv,
SummaC-ZS, AlignScore, MiniCheck, and UniEval give **inconsistent scores for
semantically equivalent summaries** on long documents; **AlignScore and SummaC-ZS are
least reliable**, UniEval/MiniCheck more (not fully) robust. → We score at the
**cell↔evidence-span** level, and **ensemble** checkers rather than trust one.

## B. RAG evaluation frameworks

| Framework | Faithfulness definition | RF/RB | Note | Cite |
| --- | --- | --- | --- | --- |
| ★ **RAGAS** | Fraction of answer statements entailed by retrieved context (`|V|/|S|`) | RF | Original paper = **3 RF metrics** (faithfulness, answer relevance, context relevance). `context_recall`/`answer_correctness` were **added later in the library and need ground truth** — do *not* cite them as reference-free | arXiv 2309.15217 (EACL 2024) |
| ★ **TREC 2024 RAG "support"** | Does each cited doc support each answer sentence? 3-level (full/partial/none) | RF | Citation-grounded **attribution** metric; our provenance model borrows this rubric | arXiv 2504.15205 (SIGIR 2025) |
| ARES / TruLens "RAG triad" / RGB | Context relevance, groundedness, answer relevance | RF | Requested but no claim survived verification — treat as *to-review*, not established here | (unverified) |

## C. Hallucination detection & attribution

| Method | Idea | RF/RB | Note | Cite |
| --- | --- | --- | --- | --- |
| ★ **SelfCheckGPT** | Draw multiple stochastic samples; consistent ⇒ factual, divergent ⇒ hallucinated. Zero-resource, black-box | RF | **Directly operationalizes the temperature effect** — sampling variance *is* the signal. Pairs with our temperature study | arXiv 2303.08896 (EMNLP 2023) |
| **FaithJudge** | LLM-judge prompted with human-annotated peer responses (hallucination spans, labels) | RB | On FaithBench: 84.0% balanced acc / 82.1% F1 vs Vectara HHEM-2.1 (52.6% / 32.9%). Strong but needs annotated exemplars; not apples-to-apples | arXiv 2505.04847 (EMNLP 2025 Industry) |

## D. LLM-as-judge reliability (for faithfulness scoring)

- **TREC support judging:** GPT-4o matches human from-scratch support judgments 56% of
  the time (72% with post-editing); an independent human correlated *better* with GPT-4o
  than with another human ⇒ LLM–human agreement is **within human–human range**. (arXiv
  2504.15205)
- **Judge's Verdict:** LLM judges track human factuality raters with Pearson up to ~0.85,
  far above exact-match/F1. (arXiv 2510.09738)
- **Implication:** LLM-judge is viable for faithfulness *if* guarded — different model
  family than the summarizer (avoid self-preference), fixed rubric, low judge
  temperature, judge self-consistency, and a human calibration set (our P5).

## E. Biomedical / clinical-genetics extraction benchmarks

| Benchmark / system | What it does | Metrics | Relevance | Cite |
| --- | --- | --- | --- | --- |
| ★ **AutoPM3 / PM3-Bench** | RAG variant extractor (Text2SQL + variant-specific retriever; **processes tables and text separately**); 1,027 ClinGen variant–publication pairs for ACMG/AMP PM3 evidence | **variant-hit accuracy** (86.1%), **in-trans recall** (72.5%) | Closest prior art for **mutation-level** extraction incl. PDF tables. We borrow the table/text separation and the hit-accuracy/recall framing | bioRxiv 2024.10.29.621006; Bioinformatics btaf382; github HKU-BAL/AutoPM3 |
| ★ **CaseReportBench** | Dense structured extraction from **138 clinical case reports**, 14 system categories, IEM/rare-disease focus | field-level **precision/recall/F1** vs expert annotation | Closest prior art for **clinical-case** field extraction; our case schema mirrors its category structure | arXiv 2505.17265 (MLHC 2025) |
| **CGBench** | ClinGen-derived: can LLMs extract & score evidence under ACMG/ClinGen-style instructions | **LLM-as-judge** vs curator explanations | Same domain + judge methodology; *to-review* (lower verification) | arXiv 2510.11985 |
| BioASQ / PubMedQA / MedHELM / tmVar / SciFact / ClinVar / GTR | QA, variant NER, holistic med eval, fact-checking, curated variant records | task-specific | Requested; not individually verified in this sweep — **absence = verification survivorship, not lack of literature**. tmVar/ClinVar/GTR feed our *source inventory* (docs/02) | (to-review) |

## F. Structured-output / table-extraction fidelity

| Method | Metric | Note | Cite |
| --- | --- | --- | --- |
| ★ **Schema-Driven IE from heterogeneous tables** | **Cell-F1 / Tuple-F1 / Page-F1** | Cell/tuple-level P/R/F1 skeleton for scoring extracted tables against a schema. We compute these against the *source-derived inventory* (silver), since we are reference-free | EMNLP Findings 2024 (aclanthology 2024.findings-emnlp.600) |

## G. What we adopt (and why)

1. **Cell-level, reference-free faithfulness** via an *ensemble*: exact/normalized value
   grounding (cheap, high-precision for HGVS strings) + an NLI checker (MiniCheck/AlignScore)
   + an LLM-judge "support" call (TREC 3-level) for hard cells. — §A, §B, §F.
2. **Provenance/attribution** scored with the TREC 3-level support rubric against the
   cited (or retrieved) evidence span. — §B.
3. **Completeness** as coverage of a **source-derived fact inventory** (variant detectors
   + the paper's own tables + NER), framed with Cell/Tuple-F1 style recall. — §E, §F.
4. **Self-consistency (SelfCheckGPT)** across samples/temperatures as a stability signal
   and the backbone of the temperature study. — §C.
5. **Guarded LLM-judge** (cross-family, fixed rubric, self-consistent, human-calibrated).
   — §D.
6. **Ensemble + agreement reporting**, and cell-level (not whole-doc) scoring, to counter
   long-document metric degradation. — §A caveat.

Full metric formulas and the experiment matrix are in `docs/02`.
