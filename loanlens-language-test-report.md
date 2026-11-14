# LoanLens — 22-language synthetic API tests (original matrix and rerun)

**Date:** 13 November 2026  
**Environment:** public GitHub Pages frontend and live Render API (`https://loanlens-api-0lrc.onrender.com`)  
**Backend model shown by API:** Gemini 3.5 Flash-Lite  
**Scope:** one synthetic education-loan case, translated to each scheduled language; submitted to `POST /analyse/text` with the corresponding language hint. No real borrower information used. Responses were checked for successful status, detected language, expected script, extraction of the co-applicant income-proof issue, and non-empty next steps.

## Result

- **20 passed** the automated functional checks: Assamese, Bengali, Bodo, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri/Meitei, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Tamil, Telugu, and Urdu.
- **Dogri — failed twice:** both the original request and one retry returned HTTP 503 with the generic fail-safe message. The backend did not return a canned analysis.
- **Sindhi — partial:** HTTP 200; the API detected Sindhi and extracted the intended missing co-applicant income-proof reason, but the answer was mostly Arabic script with a few Devanagari fragments, despite a Devanagari Sindhi prompt. Treat output-script selection as unreliable for this case.

Hindi was correctly counted as a pass: the API returned `hi` (the ISO language code) rather than the word “Hindi”; the script and analysis matched the case.

## Important coverage limitation

The live page currently exposes **14 selectable language options**, not all 22. The other eight—Bodo, Dogri, Konkani, Maithili, Manipuri/Meitei, Nepali, Sanskrit, and Sindhi—were tested against the API directly with language hints, not through a selectable frontend option. This test therefore verifies backend handling, not complete UI selection/use for all 22.

## Reliability caveats

Translations for this matrix were machine-generated and were not reviewed by native speakers. The script check is a codepoint-based heuristic; it cannot assess fluency, nuance, or whether financial guidance is correct. This is a single synthetic scenario per language, not comprehensive language validation. Some generated advice mentions common income documents, but the test did not verify lender-specific requirements. Do not interpret this result as proof of fairness or as legal/financial advice.

## Evidence

Case-level detected language, extracted reason, answer excerpts, statuses, script checks, and failure details are in [the JSON matrix](./loanlens-language-matrix.json). Request IDs are omitted.

## Full live API rerun — 14 November 2026

The same 22 machine-translated synthetic cases were submitted sequentially to the live API with their language hints after the evidence-grounding prompt and postal-code review-flag refinement were deployed. **22/22 passed** the bounded smoke-test checks: HTTP 200, intended language identification, structured native and English explanations, 2–4 next steps, and at least 80% of answer letters in the expected script. One transient server/network failure recovered on a single retry. Dogri now returned 89/89 Devanagari letters; Sindhi returned 191/191 Arabic-script letters. The complete per-language run is in [the latest JSON matrix](./loanlens-language-matrix-latest.json).

## Focused retests — 14 November 2026

Before the full rerun completed, the earlier Dogri and Sindhi cases were each retested directly; both returned HTTP 200, the intended detected language, and non-empty explanations and next steps (Dogri: 3; Sindhi: 2). These were repeated as part of the full matrix above. The live frontend still exposes 14 selector choices; the draft PR branch exposes 22. These API checks do not establish native-speaker quality, fluency, nuance, or legal correctness.
