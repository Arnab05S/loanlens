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

### Try it

1. Open [LoanLens](https://arnab05s.github.io/loanlens/).
2. Type what happened, upload a PDF/image, or take a photo of a rejection notice.
3. Review the extracted facts, explanation, and suggested next steps. Check important requirements with the lender or an appropriate adviser.

**Use synthetic or redacted material when possible.** Do not upload unredacted Aadhaar, PAN, account numbers, phone numbers, or other sensitive identifiers. Documents are sent to Google’s Gemini service for analysis; review the relevant provider privacy terms before submitting personal material.

## Current capabilities

| Area | Current implementation |
| --- | --- |
| Text | Case-specific analysis through the FastAPI backend, with a language hint where available |
| Documents | PDF, JPEG, PNG, and WEBP uploads; maximum 20 MB |
| AI response | Structured extraction, explanation, and next-step suggestions; service errors are shown instead of a fallback conclusion |
| Browser UI | Static HTML, CSS, and JavaScript; no frontend build step |
| Model | Gemini 3.5 Flash-Lite by default, with configured model fallbacks |

### Language coverage — status matters

The public page currently offers **14 selectable languages**: Assamese, Bengali, Gujarati, Hindi, Kannada, Kashmiri, Malayalam, Marathi, Odia, Punjabi, Santali, Tamil, Telugu, and Urdu. Bodo, Dogri, Konkani, Maithili, Manipuri/Meitei, Nepali, Sanskrit, and Sindhi are not selectable in the current UI. Unicode input and a language hint do not, by themselves, prove that every language is handled accurately. Treat full 22-language quality as unvalidated until the language-specific test suite and native-speaker review are complete.

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

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check |
| `POST` | `/analyse/text` | Analyze text and optional language hint |
| `POST` | `/analyse/document` | Analyze a PDF or supported image upload |
| `GET` | `/docs` | Interactive API documentation |

Example health check:

```bash
curl https://loanlens-api-0lrc.onrender.com/health
```

## Publishing and deploys

The two hosted parts have separate automatic deploy sources:

- **Website:** GitHub Pages publishes the repository’s `main` branch root. A commit to the web files or assets on `main` triggers the Pages build-and-deployment workflow.
- **API:** the Render `loanlens-api` service builds from `backend/` on branch `fix/real-analysis`. Render is set to auto-deploy on relevant commits, so changes inside `backend/` trigger an API build; documentation, root HTML, and image-only changes outside `backend/` do not need to rebuild the API. Keep `GEMINI_API_KEY` in Render’s server-side environment/secret settings.

After a web change, verify [the live site](https://arnab05s.github.io/loanlens/). After a backend change, check [API health](https://loanlens-api-0lrc.onrender.com/health) and the Render deployment status. **A commit to `main` does not, by itself, update the Render branch, and a commit to `fix/real-analysis` does not update GitHub Pages.** Keep the branches in sync when touching shared HTML, or merge/reconfigure only after reviewing the current draft pull request. The live UI and API must both point at the intended release.

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
