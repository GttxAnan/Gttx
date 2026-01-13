# Aurora - PDF to Audio Converter

A beautiful, "Aurora" themed web application to convert PDF documents into natural-sounding audiobooks using Google Cloud TTS and Microsoft Edge TTS.

## Features
- **Drag & Drop Interface**: Easy to use file upload.
- **Dual Engines**: 
  - **Premium Journey**: Uses Google Cloud's high-quality "Journey" voices.
  - **Standard Edge**: Uses Microsoft Edge's online TTS (free fallback).
- **Smart Chunking**: Intelligent text splitting to maintain sentence continuity.
- **Progress Tracking**: Real-time progress bar and status updates.

## Prerequisites
- **Python 3.10+** (The application requires Python 3.6+ for syntax features, tested on 3.10).
- **Google Cloud Credentials** (Optional, for Premium engine): Set up `GOOGLE_APPLICATION_CREDENTIALS` environment variable.

## Installation

1.  **Clone the repository** (if not already done).
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If you have multiple Python versions, ensure you use the one for Python 3.x (e.g., `pip3` or `py -m pip`).*

## How to Run

1.  **Start the server**:
    ```bash
    py pdfAudioConverter.py
    ```
    *Or if you don't have the `py` launcher:*
    ```bash
    python3 pdfAudioConverter.py
    ```

2.  **Open the application**:
    Open your web browser and navigate to:
    [http://localhost:5000](http://localhost:5000)

## Usage
1.  Select your preferred TTS engine (Premium or Standard).
2.  Drag and drop a PDF file onto the upload area.
3.  Wait for the conversion to complete.
4.  Download the generated MP3 file.

## Troubleshooting
- **SyntaxError: invalid syntax**: You are likely running an old version of Python (e.g., 2.7). Please use Python 3.10+ via `py` or `python3`.
- **ModuleNotFoundError**: Ensure you installed dependencies with `pip install -r requirements.txt`.
