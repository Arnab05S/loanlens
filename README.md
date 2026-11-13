# LoanLens — loan rejection explainer for India

LoanLens extracts information from a rejection notice or a user description and suggests practical follow-up steps. It is an informational prototype, not a lender decision system, legal service, or statistical fairness audit. A single application cannot establish discrimination.

## Current setup

- Frontend: static HTML/JavaScript in both index.html and frontend/index.html (kept identical for the two GitHub Pages layouts).
- Backend: FastAPI in backend/main.py.
- AI: Google GenAI Python SDK (google-genai), default model gemini-3.8-flash.
- No sample/demo result is returned when the API is absent. The UI shows a configuration error instead.

## Local run

1. Create a virtual environment and install backend/requirements.txt.
2. Set GEMINI_API_KEY in the backend environment (never put it in the browser or commit it).
3. Run uvicorn main:app --app-dir backend --reload --port 8000 from the repository root.
4. Set window.LOANLENS_API_BASE to http://localhost:8000 in the frontend before use.
5. For local CORS, set CORS_ORIGINS to the frontend origin. The default is permissive for a simple static prototype; production should set the exact site origin.

## Deploying

Deploy the backend separately (for example, Cloud Run). Configure GEMINI_API_KEY as a server-side secret and set CORS_ORIGINS to the exact GitHub Pages origin. Set the frontend API base to the HTTPS backend URL. GitHub Pages is static hosting and cannot keep an AI API key secret. A working end-to-end deployment requires both a live backend and correct CORS/API URL configuration.

The repository does not include a verified live backend URL. Do not claim the public demo performs AI analysis until deployment has been configured and checked.

## Supported inputs

Text, PDF, JPEG, PNG, and WEBP. Maximum upload size is 20 MB. Other formats (including HEIC and Word documents) are not accepted by the API.

## Safety and limitations

- Extraction is per request; errors and unreadable/empty documents fail instead of receiving a canned result.
- Identity characteristics are not converted into a bias score. The app does not have lender-wide applicant data for statistical comparisons.
- Never upload unredacted Aadhaar/PAN, bank account, or phone details. Files are sent to Google’s AI service for analysis; review provider terms and privacy policy before public use.
- RBI escalation eligibility and applicable law depend on circumstances. Check current official guidance and seek qualified advice where needed.
- Before public use, add abuse/rate limits, privacy and retention review, accessibility and language QA, and tests against representative redacted examples.

## Test

From the backend directory with dependencies installed: python -m unittest test_main.py
