# Scientific policy — enforce in code, review and UX

## Scientific source classifications

| Type | Meaning | What it does NOT prove |
|---|---|---|
| OBSERVED | Directly retrieved NASA or other measured/gridded observation | Cause of farm damage or field-scale measurement when source is coarse |
| FARMER_REPORTED | Information volunteered by farmer | Independent measurement unless verified |
| LITERATURE_METADATA | Verifiable article identity/DOI | That the article supports a given claim |
| LITERATURE_REVIEWED | Human-checked claim/method/result with study context | Universal transferability |
| HYPOTHESIS | A possible explanation with pros/cons | Causality or quantified certainty |
| MODEL_SCENARIO | Output of named computational assumptions/model | Observed outcomes, guaranteed water savings or crop yield |
| ILLUSTRATIVE | Synthetic or educational example, conspicuously labeled | Real observations |

## Sources

NASA POWER first, with exact endpoint parameters and checksum. GPM/HLS when scheduled in the roadmap and with resolution limitations. Literature search via OpenAlex/Crossref, DOI verification and license-aware full text. Context-sensitive local soil info should distinguish farmer measurements from modeled soil maps.

## Forensics methodology standards

- Use comparable and clearly defined reference years; separate seasonality and anomalous periods.
- Warn if coverage is insufficient, satellite/modeled data resolution too coarse or local data missing.
- Do not convert co-occurrence into proof of a cause. Provide rival hypotheses and evidence gaps.
- Rotation comparisons must obey farmers' constraints, seasonal windows, crop sequences and limitations; always include current rotation and at least two alternatives.
- No auto-generated percentage water savings or yield gain unless backed by an appropriate validated model, calibrated inputs and uncertainty intervals.
- No LLM-authored scholarly citation or effect size without verification; cite DOI/metadata and reviewed evidence passages with accurate context.
- Historical scenario replay is not a future weather forecast.

## Review levels

Scientific inference change -> documented method, tests, scientific review and ADR when architectural. A wording/UI change -> reviewer confirms status/uncertainty labels. Data source/quality changes -> update source manifest, API and regression tests.
