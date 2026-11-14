<div align="center">
  <img src="assets/loanlens-brand.jpg" alt="LoanLens — Fair lending, for everyone" width="100%">
  <h1>LoanLens</h1>
  <p><strong>Understand a loan rejection. Know what to check next.</strong></p>
  <p>An AI-powered explainer for people in India reviewing a loan rejection letter or describing what happened.</p>
  <p>
    <a href="https://arnab05s.github.io/loanlens/">Open the live site</a> ·
    <a href="https://loanlens-api-0lrc.onrender.com/health">API health</a> ·
    <a href="https://loanlens-api-0lrc.onrender.com/docs">API docs</a>
  </p>
</div>

---

## What LoanLens does

LoanLens reads a borrower’s description or a rejection notice, extracts the case details, explains the stated reason in plain language, and suggests practical questions or next steps. It is an informational aid—not a lender, lawyer, credit bureau, or statistical fairness audit. A single application cannot prove discrimination, and lender-specific requirements should be confirmed with the lender.

The **Review Priority Score (0–100)** is a deterministic, unvalidated triage heuristic computed from explicit evidence flags—not a probability of discrimination or an AI model’s finding of unfairness. Its fixed rubric uses the strongest matching signal weight plus 5 points per additional distinct signal, capped at 100:

| Evidence signal in the submitted case | Base weight |
| --- | ---: |
| Explicit decision link to a personal characteristic | 95 |
| Unexplained community/residential-profile criterion | 85 |
| Explicit geography/serviceability criterion | 70 |
| Stated refusal to disclose scoring/underwriting basis | 35 |
| Missing specific basis or review route | 30 |
| Reason too general to verify | 25 |
| No predefined signal | 0 |

A score of 0 means no predefined review signal was found; it does **not** establish that the decision was fair. Gender, occupation, location, or language alone do not raise the score. Non-rejection, unreadable, unsupported, or insufficient material receives no score. Live synthetic smoke tests on 14 November returned 0 for a clear threshold-only rejection, 100 for explicit geography plus community rules with opaque/missing-review details, and 75 for a PNG notice citing service-area restriction and missing review details. These confirm the end-to-end output wiring only; the weights are not empirically calibrated or statistically validated.

### Try it

1. Open [LoanLens](https://arnab05s.github.io/loanlens/).
2. Type what happened, choose a supported file, use the camera, or drag a file into the upload area.
3. Review the extracted facts, explanation, and suggested next steps. Check important requirements with the lender or an appropriate adviser.

**Use synthetic or redacted material when possible.** Do not upload unredacted Aadhaar, PAN, account numbers, phone numbers, or other sensitive identifiers. LoanLens does not keep a permanent copy of uploaded files, but their content is sent to Google’s Gemini service for analysis; review the relevant provider privacy terms before submitting personal material.

## Current capabilities

| Area | Current implementation |
| --- | --- |
| Text | Case-specific analysis through the FastAPI backend, with a language hint where available |
| Documents | PDF, JPEG/PNG/WEBP/HEIC/HEIF/BMP/GIF/TIFF, DOC/DOCX/ODT, XLS/XLSX, PPT/PPTX, TXT/MD/CSV/JSON/HTML/XML/RTF, EML, and ZIP; 20 MB per upload |
| File handling | PDFs/photos use Gemini vision; DOCX/ODT/PPTX text and embedded images are extracted; XLSX cell values are read; legacy DOC/XLS/PPT are sent directly to Gemini (provider parsing not live-verified); ZIPs analyse up to 12 supported items within a 50 MB expanded-size limit |
| Fail-safe behavior | Unsupported, password-protected, corrupt, oversized, mismatched, or unreadable uploads return a clear error rather than a canned analysis |
| AI response | Structured extraction, explanation, case-specific next steps, qualitative evidence flags, and one deterministic Review Priority Score; not a statistical bias probability |
| Browser UI | Static HTML, CSS, and JavaScript; no frontend build step |
| Model | Gemini 3.5 Flash-Lite by default, with configured model fallbacks |

### Language coverage — status matters

The public page currently offers **14 selectable languages**: Assamese, Bengali, Gujarati, Hindi, Kannada, Kashmiri, Malayalam, Marathi, Odia, Punjabi, Santali, Tamil, Telugu, and Urdu. Bodo, Dogri, Konkani, Maithili, Manipuri/Meitei, Nepali, Sanskrit, and Sindhi are not selectable in the current UI. The 13 November synthetic API matrix tested one machine-translated education-loan case per scheduled language: **20 passed** basic functional checks, **Dogri failed** twice with HTTP 503, and **Sindhi was partial** because its output script was unreliable. On 14 November, a full API-only rerun with those same 22 synthetic cases passed **22/22**: HTTP 200, intended language detection, structured native and English explanations, 2–4 next steps, and at least 80% of native-answer letters in the expected script. One transient server/network error required a single retry. The earlier Dogri and Sindhi gaps also passed their focused retests. This tests one machine-translated case per language—not native-speaker fluency, nuance, or legal correctness. Both the live `main` page and current draft branch expose 14 choices; the 22-case matrix exercised the API directly, not all browser selector options. See `loanlens-language-test-report.md` and `loanlens-language-matrix-latest.json` for the detailed results.

## How it is built

- `index.html` and `frontend/index.html` are the mirrored static web entry points.
- `backend/main.py` is the FastAPI service; dependencies are listed in `backend/requirements.txt`.
- The browser calls the backend’s text and document endpoints. The Gemini API key stays server-side as the Render `GEMINI_API_KEY` secret; never put it in HTML, JavaScript, or Git.
- The app has no lender-wide decision dataset, so it cannot produce a defensible statistical bias score or establish that an individual decision was discriminatory.

## Run locally

Use Python 3.11+ and run the API from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:GEMINI_API_KEY = "your-key-in-your-local-shell-only"
uvicorn main:app --app-dir backend --reload --port 8000
```

Serve the static page from the repository root in a second terminal:

```powershell
python -m http.server 5500
```

For local testing, set the front-end API URL to `http://localhost:8000` using `window.LOANLENS_API_BASE` before the page’s configuration script runs, or use the local value in `API_BASE`. The backend’s `CORS_ORIGINS` must allow the page’s origin. Never commit a real key or `.env` file.

## Run tests

From the repository root, install the backend dependencies and run the full mocked API and upload-parser suite:

```bash
python -m pip install -r backend/requirements.txt
python -m unittest discover -s backend -v
```

The suite uses synthetic fixtures only; it does not call Gemini or require a live API key.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check |
| `POST` | `/analyse/text` | Analyze text and optional language hint |
| `POST` | `/analyse/document` | Analyze a supported document, photo, email, spreadsheet, text file, or ZIP upload |
| `GET` | `/docs` | Interactive API documentation |

Example health check:

```bash
curl https://loanlens-api-0lrc.onrender.com/health
```

## Publishing and deploys

The two hosted parts have separate deploy sources:

- **Website:** GitHub Pages publishes the repository’s `main` branch root. The latest Pages workflow completed successfully, and the logo/API configuration are live.
- **API:** the Render `loanlens-api` service builds from `backend/` on branch `fix/real-analysis`. Render’s **On Commit** setting did not start recent builds, so `.github/workflows/deploy-render-backend.yml` now triggers the Render deploy hook on backend changes in that branch. The workflow’s repository secret is `RENDER_DEPLOY_HOOK` (separate from the server-side Render secret `GEMINI_API_KEY`). The workflow and hook-triggered deployment have both been verified. Documentation, root HTML, and image-only changes outside `backend/` do not need to rebuild the API.

After a web change, verify [the live site](https://arnab05s.github.io/loanlens/). After a backend change, confirm the GitHub Actions workflow and Render deployment complete, then check [API health](https://loanlens-api-0lrc.onrender.com/health). **A commit to `main` does not, by itself, update the Render branch, and a commit to `fix/real-analysis` does not update GitHub Pages.** Keep the branches in sync when touching shared HTML, or merge/reconfigure only after reviewing the current draft pull request. The live UI and API must both point at the intended release.

## Repository layout

```text
loanlens/
├── assets/                 # README and site branding
├── backend/
│   ├── main.py             # FastAPI + Gemini analysis
│   └── requirements.txt
├── frontend/
│   ├── assets/             # Branding for standalone frontend hosting
│   └── index.html          # Mirrored static UI
├── index.html              # GitHub Pages entry point (main branch root)
└── README.md
```

Contact:
This website is maintained and created by [Arnab05S](https://github.com/Arnab05S/). Open an issue on GitHub for questions or bug reports or any other assistance.
