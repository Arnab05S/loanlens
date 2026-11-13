# LoanLens — loan rejection explainer for India

LoanLens extracts information from a rejection notice or a user description and gives a case-specific explanation and next-step suggestions. It is an informational prototype, not a lender decision system, legal service, or statistical fairness audit. A single application cannot establish discrimination.

## Current setup

- Frontend: static HTML/JavaScript in both index.html and frontend/index.html. This backend-only refinement does not change the UI.
- Backend: FastAPI in backend/main.py.
- AI: Google GenAI Python SDK (google-genai), default model gemini-3.8-flash.
- One structured model call per request returns extracted facts, explanation, questions when needed, and next steps.
- No canned/sample result is returned when the API is unavailable.

## Local run

1. Create a virtual environment and install backend/requirements.txt.
2. Set GEMINI_API_KEY in the backend environment (never put it in the browser or commit it).
3. Run uvicorn main:app --app-dir backend --reload --port 8000 from the repository root.
4. Set window.LOANLENS_API_BASE to http://localhost:8000 in the served frontend.
5. Set CORS_ORIGINS to the exact frontend origin for production.

## Deploying

Deploy the backend separately (for example, Cloud Run). Store GEMINI_API_KEY as a server-side secret. Set CORS_ORIGINS to the exact GitHub Pages origin and configure the frontend API base to the HTTPS backend URL. GitHub Pages is static hosting and cannot keep an AI API key secret. End-to-end operation requires a live backend and correct CORS/API URL configuration. The repository does not include a verified live backend URL.

## Supported inputs

Text, PDF, JPEG, PNG, and WEBP. Maximum upload size is 20 MB. HEIC and Word documents are not accepted by the API.

## Safety and limitations

- The response must include case facts, a valid explanation, and 1-4 next steps; malformed model responses fail as service errors rather than being presented as conclusions.
- The original user text and extracted facts are supplied together to the answer prompt so the answer can address that case. Submitted content is treated as untrusted data, not instructions.
- Identity characteristics are not converted into a bias score. This app has no lender-wide applicant dataset for statistical comparisons.
- Files are sent to Google’s AI service for analysis. Avoid uploading unredacted Aadhaar/PAN, bank account, or phone details. Review provider terms/privacy before public use.
- RBI escalation eligibility and applicable law depend on circumstances; check official guidance.
- Before public use, add abuse/rate limits, privacy/retention review, accessibility and language QA, and representative evaluations.

## Test

From the backend directory with dependencies installed: python -m unittest test_main.py. The suite covers per-case answer variation and service failure behavior with mocked model responses; it does not prove real-world model accuracy.
