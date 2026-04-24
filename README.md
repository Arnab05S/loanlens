LoanLens — AI Loan Fairness Auditor for India
> Google Solution Challenge 2026 · Problem theme: **Unbiased AI Decision**
AI-powered loan rejection analyser that helps any ordinary Indian citizen — in any of India's 22 scheduled languages — check whether their loan was rejected unfairly, and exactly what to do about it.
---
Submission checklist
[ ] GitHub repository (this repo) — public
[ ] Live MVP link — 'https://arnab05s.github.io/loanlens/'
[ ] Demo video — `loanlens_demo_walkthrough.html`
[ ] Project deck — see `/docs/deck.pdf`
---
Project structure
```
loanlens/
├── backend/
│   ├── main.py          ← complete FastAPI backend (single file)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html       ← complete citizen-mode UI (single file)
├── docs/
│   ├── loanlens_citizen_mode.html   ← full prototype demo
│   └── loanlens_demo_walkthrough.html
└── README.md
```
---
Local development (test before deploying)
```bash
# Backend
cd backend
pip install -r requirements.txt
echo "GEMINI_API_KEY=your_key_here" > .env
uvicorn main:app --reload --port 8000
# Visit http://localhost:8000/docs to test all endpoints

# Frontend — just open in browser
open frontend/index.html
# Set API_BASE = "http://localhost:8000" in the <script> config block
```
---
Deploy in 3 steps
Step 1 — Deploy backend to Google Cloud Run (~15 min)
```bash
# Install gcloud CLI from https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID

# Set your Gemini API key as a secret
gcloud secrets create gemini-api-key --data-file=- <<< "YOUR_GEMINI_API_KEY"

# Deploy from the backend/ folder
cd backend
gcloud run deploy loanlens-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest \
  --memory 512Mi \
  --timeout 60s

# Copy the Service URL printed at the end — looks like:
# https://loanlens-backend-XXXX-as.a.run.app
```
Step 2 — Set backend URL in frontend (~1 min)
Open `frontend/index.html` and find the config block near the top:
```javascript
const API_BASE = "";  // ← paste your Cloud Run URL here
// becomes:
const API_BASE = "https://loanlens-backend-XXXX-as.a.run.app";
```
Step 3 — Deploy frontend to GitHub Pages (~5 min)
```bash
# From repo root
git init
git add .
git commit -m "Initial LoanLens submission"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/loanlens.git
git push -u origin main

# In GitHub:
# Settings → Pages → Source → Deploy from branch → main → /frontend → Save
# Your live URL: https://YOUR_USERNAME.github.io/loanlens
```
---
What to submit on Hack2Skill
Field	Value
Problem statement	Unbiased AI Decision — detecting and explaining bias in Indian loan rejections
Solution overview	AI-powered citizen fairness auditor using Gemini 1.5 Flash + Python bias engine + Firebase
Prototype link	`https://arnab05s.github.io/loanlens/`
GitHub repo	`https://github.com/arnab05s/loanlens`
Demo video	Upload the recorded screencast (≤20 min)
---
Tech stack
Layer	Technology
AI extraction	Gemini 1.5 Flash (multimodal — PDF, image, text)
AI explanation	Gemini 1.5 Flash (plain-language, all 22 languages)
Bias engine	Python + Fairlearn + India-specific rule database
Backend	FastAPI + Cloud Run
Frontend	Vanilla HTML/JS (no build step — GitHub Pages ready)
Storage	Firebase Firestore (optional)
---
Supported input types
Type	How it works
PDF	Gemini reads directly as inline_data
Image / photo	Gemini Vision handles blur, rotation, low light
Text	Auto-detect language, extract and score
---
Languages supported (all 22 scheduled languages of India)
Assamese · Bengali · Bodo · Dogri · Gujarati · Hindi · Kannada · Kashmiri · Konkani · Maithili · Malayalam · Manipuri · Marathi · Nepali · Odia · Punjabi · Sanskrit · Santali · Sindhi · Tamil · Telugu · Urdu
---
Test the API
After deploying, test at: `https://loanlens-backend-XXXX-as.a.run.app/docs`
```bash
# Health check
curl https://loanlens-backend-XXXX-as.a.run.app/health

# Text analysis
curl -X POST https://loanlens-backend-XXXX-as.a.run.app/analyse/text \
  -H "Content-Type: application/json" \
  -d '{"text": "मेरा लोन अस्वीकार हो गया। बैंक ने कहा क्षेत्र सेवायोग्य नहीं है।"}'

# Document upload
curl -X POST https://loanlens-backend-XXXX-as.a.run.app/analyse/document \
  -F "file=@rejection_letter.pdf"
```
---
Team
4 members · India · Google Solution Challenge 2026
