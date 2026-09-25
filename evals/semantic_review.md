# Source review of the semantic evaluation

This is an **assistant-performed review**, not an independent human or clinical review. It compares saved answers with retrieved passages and annotated PDF text in [semantic_results.json](semantic_results.json). Raw judge scores are preserved, including disagreements below. No answers were regenerated to improve the recorded scores.

## Scope and findings

Reviewed five answerable cases spanning thresholds, combination therapy, diagnostic tables, first-line treatment, and an insulin flowchart, plus all three out-of-scope cases. The automated judge flagged no cases for answer or citation problems; sampling nevertheless found weaknesses. This is why the automated 2/2 means must not be described as 100% verified accuracy.

| Case | Source-based observation | Review conclusion |
| --- | --- | --- |
| `htn-threshold` | Retrieved hypertension PDF pages 9 and 19 support the stated thresholds and the distinction between strong and conditional recommendations. | No material discrepancy found in the sampled answer. |
| `htn-combination` | Retrieved PDF pages 10/25 support the conditional recommendation and drug classes; pages 26/27 support the additional rationale and cited observational results. | Main answer is supported. It is longer than necessary; future answers could more explicitly retain the source's limited randomized evidence for clinical outcomes. |
| `dm-diagnostic-criteria` | The answer follows HEARTS-D PDF page 13 and the retrieved testing discussion. However, retrieved passages 1 and 5 are contents lists and passage 3 describes intended users. Only passages 2 and 4 directly supply diagnostic details. | Disagree with context relevance 2/2; **1/2 (mixed)** better matches the rubric. Answer support is substantially stronger than retrieval precision. |
| `dm-metformin` | Passages 1 and 2 support the initial treatment and the cited protocol step. Passage 3 is an annex contents entry; passages 4 and 5 primarily concern escalation after treatment failure. | Disagree with context relevance 2/2; **1/2 (mixed)** is more appropriate. The answer preserves the condition for the alternative first-line agent. |
| `dm-insulin-protocol` | Passage 1 supports the initial steps, but its extracted flowchart stops before several actions that remain visible in full reference page 29. The answer says to follow reduction protocols without giving those actions, and omits subsequent escalation and monitoring branches. Other retrieved passages include contents and audience descriptions. | Disagree with answer quality and context relevance 2/2; **1/2 for each** better represents an incomplete summary with mixed context. This is a chunking/retrieval completeness limitation, not evidence that the full protocol was covered. |
| `unanswerable-covid` | The answer states that the retrieved material does not contain the requested information and provides no regimen. | Appropriate refusal on this case. |
| `unanswerable-pediatric-cancer-chemo` | The answer refuses without inventing a schedule, but attaches all five source IDs to the absence-of-information statement. | Appropriate refusal; the IDs identify searched passages, not evidence for a treatment answer. Citation-support `null` is reasonable for this refusal, but the presentation could be clearer. |
| `unanswerable-ehr` | The answer explicitly states that the retrieved sources do not describe the requested integration and invents no setup steps. | Appropriate refusal on this case. |

These are proposed review ratings on a sample, not a replacement aggregate over all 17 cases. No independent clinical expert has validated this application.

## Interpretation and follow-up

The run demonstrates a reproducible evaluation workflow covering retrieval, answer quality, groundedness, citation support, and refusals. It also demonstrates a limitation of same-model judging: the judge can overlook irrelevant context and incomplete answers even when full reference pages are supplied.

Useful future improvements are removing contents pages from retrieval, retaining complete flowchart branches in chunks, and adding independent reviewers and held-out questions. Re-evaluate after those changes. The recorded results should remain a baseline, not be overwritten to conceal these findings.

## Cost and reproducibility

- Model: `gemini-3.5-flash-lite`, separate generation and judging calls.
- 17 questions, 34 completed requests, 80,177 input tokens, 4,598 output tokens.
- Estimated standard list-price cost: **$0.0355481**, excluding any free-tier benefits, taxes, or discounts.
- The evaluator uses a $0.10 estimated cumulative cache budget, output caps, no automatic retries, and cache-only operation unless `--live` is specified.
- Raw answers, sources, reference pages, model rubric, data hashes, score denominators, and token usage are saved in the JSON report. Provider credentials are not included.
