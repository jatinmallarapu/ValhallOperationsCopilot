# Evaluation protocol

Run `make eval` after installing the project. The command executes all twenty
versioned questions through FastAPI and the compiled LangGraph, checks the final
route and expected executed tool, and saves `runs/routing.json`. Timing includes
in-process HTTP and SSE serialization. It excludes startup, networking, pgvector,
external LLM latency and CDF acquisition.

The initial local run produced **20/20 routes**, **20/20 expected tools**, and
**61.77 ms mean response time** on the synthetic offline corpus. This small,
author-curated regression is not independent model evaluation and must not be
presented as general routing accuracy. The router was developed with these cases.
An honest next benchmark is a held-out collection of paraphrases and mixed intents,
with separate measures for retrieval relevance, answer faithfulness, unsupported
claims, no-data abstention, latency percentiles and provider failure behavior.

The generated pressure trace has deliberately planted deviations. Detecting them
does not establish industrial anomaly-detection recall or diagnose a compressor.
No operational ground truth or approved maintenance documents are present.

Unit/API tests cover scope boundaries, graph/tool traces, empty windows, malformed
requests, synthetic document labels, cyclic asset rejection and a mocked CDF
hourly aggregate read. CI additionally builds the production React image and
exercises the pgvector Compose stack. The CI result is independent of any claim
about live CDF access or LLM answer quality.
