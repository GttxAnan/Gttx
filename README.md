# Aurora - PDF to Audio Converter

A beautiful, "Aurora" themed web application to convert PDF documents into natural-sounding audiobooks. Now with persistent storage and session management.

## Features
- **Drag & Drop Interface**: Easy to use file upload.
- **Dual Engines**: 
  - **Premium Journey**: Uses Google Cloud's high-quality "Journey" voices.
  - **Standard Edge**: Uses Microsoft Edge's online TTS (free fallback).
- **Session History**: Tracks your conversions during your session.
- **Cloud Storage**: Securely stores audio files (Supabase).

## Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Supabase Account** (Free tier)
- **Google Cloud Credentials** (Optional)

## Local Setup

### 1. Backend
```bash
# Create virtual env
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Configure Environment
# Create a .env file with:
# SUPABASE_URL=your_url
# SUPABASE_KEY=your_anon_key
# GOOGLE_APPLICATION_CREDENTIALS=path/to/creds.json (Optional)

# Run Server
python pdfAudioConverter.py
```

### 2. Frontend
You can serve the frontend using any static file server.
```bash
cd frontend
# Example using python
python -m http.server 3000
```
*Note: For the frontend to talk to the backend locally, you may need to configure a proxy or ensure the specific endpoints in `index.html` point to your running backend URL (e.g., http://localhost:5000).*

## Deployment (Free Tier)

### Backend (Render)
1. Fork this repo.
2. Create a **Web Service** on Render.
3. Connect repo.
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `python pdfAudioConverter.py`
6. Set Environment Variables (`SUPABASE_URL`, `SUPABASE_KEY`).
7. Deploy.

### Frontend (Vercel)
1. Create a **New Project** on Vercel.
2. Import the `frontend` directory from the repo.
3. Vercel should automatically detect the HTML project.
4. **Crucial**: Update `frontend/vercel.json` and replace `https://YOUR_BACKEND_URL` with your actual Render Backend URL.
5. Deploy.

### Database (Supabase)
See `supabase_setup.md` for SQL initialization scripts.

