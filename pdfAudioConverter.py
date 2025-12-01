import os
import uuid
import asyncio
import json
import math
import logging
import threading
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pypdf import PdfReader
import edge_tts
from google.cloud import texttospeech
from google.api_core import exceptions as google_exceptions

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
HISTORY_FILE = 'history.json'
USAGE_FILE = 'usage.json'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
tasks = {}
FREE_TIER_LIMIT = 1_000_000

# --- Helper Functions ---

def load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'total_chars': 0, 'month': datetime.now().strftime("%Y-%m")}

def save_usage(usage):
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f)

def update_usage(char_count):
    usage = load_usage()
    usage['total_chars'] += char_count
    save_usage(usage)
    return usage['total_chars']

def check_quota(char_count):
    usage = load_usage()
    if usage['total_chars'] + char_count > FREE_TIER_LIMIT:
        return False
    return True

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(entry):
    history = load_history()
    history.insert(0, entry)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history[:50], f)

def find_start_page(reader):
    patterns = [
        re.compile(r"^\s*chapter\s*1\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*introduction\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*part\s*i\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*page\s*1\s*$", re.IGNORECASE | re.MULTILINE)
    ]
    num_pages = len(reader.pages)
    check_limit = min(num_pages, 20)
    for i in range(check_limit):
        try:
            text = reader.pages[i].extract_text()
            if text:
                for pattern in patterns:
                    if pattern.search(text):
                        return i
        except: continue
    return 0

def smart_chunk_text(text, max_chars=4500):
    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            if len(paragraph) > max_chars:
                sentences = paragraph.replace('. ', '.|').replace('? ', '?|').replace('! ', '!|').split('|')
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 > max_chars:
                        if current_chunk: chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        current_chunk += " " + sentence
            else:
                current_chunk = paragraph
        else:
            current_chunk += "\n\n" + paragraph

    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

async def generate_audio_edge(text, output_file, voice="en-US-ChristopherNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def generate_audio_google(text, output_file, voice_name="en-US-Journey-D"):
    client = texttospeech.TextToSpeechClient()
    input_text = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
    with open(output_file, "wb") as out:
        out.write(response.audio_content)

async def process_pdf_async(task_id, file_path, original_filename, engine='edge'):
    try:
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 5
        tasks[task_id]['message'] = 'Analyzing PDF structure...'
        
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        start_page_index = find_start_page(reader)
        
        tasks[task_id]['message'] = f'Extracting text (starting page {start_page_index + 1})...'
        full_text = ""
        for i in range(start_page_index, total_pages):
            text = reader.pages[i].extract_text()
            if text: full_text += text + "\n\n"
            if i % 10 == 0:
                tasks[task_id]['progress'] = 5 + int(((i - start_page_index) / (total_pages - start_page_index)) * 10)

        if not full_text.strip(): raise Exception("No text found in PDF")

        tasks[task_id]['progress'] = 15
        tasks[task_id]['message'] = 'Optimizing text chunks...'
        text_chunks = smart_chunk_text(full_text)
        
        tasks[task_id]['progress'] = 20
        tasks[task_id]['message'] = f'Converting {len(text_chunks)} chunks to audio...'
        
        temp_dir = os.path.join(OUTPUT_FOLDER, task_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        semaphore_limit = 10 if engine == 'edge' else 1
        semaphore = asyncio.Semaphore(semaphore_limit) 
        fallback_triggered = False

        async def process_chunk(index, text):
            nonlocal fallback_triggered
            async with semaphore:
                chunk_filename = os.path.join(temp_dir, f"chunk_{index:04d}.mp3")
                if engine == 'google' and not fallback_triggered:
                    try:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, generate_audio_google, text, chunk_filename)
                        update_usage(len(text))
                        return chunk_filename
                    except Exception as e:
                        logger.warning(f"Google TTS error: {e}. Falling back.")
                        fallback_triggered = True
                
                await generate_audio_edge(text, chunk_filename)
                return chunk_filename

        chunk_tasks = [process_chunk(i, text) for i, text in enumerate(text_chunks)]
        completed = 0
        total_chunks = len(chunk_tasks)
        
        for future in asyncio.as_completed(chunk_tasks):
            await future
            completed += 1
            tasks[task_id]['progress'] = 20 + int((completed / total_chunks) * 70)
            msg = f'Converted chunk {completed}/{total_chunks}...'
            if fallback_triggered: msg += " (Standard Voice)"
            tasks[task_id]['message'] = msg

        ordered_chunk_files = [os.path.join(temp_dir, f"chunk_{i:04d}.mp3") for i in range(len(text_chunks))]
        valid_chunks = [f for f in ordered_chunk_files if os.path.exists(f)]

        tasks[task_id]['message'] = 'Merging audio files...'
        
        base_name = os.path.splitext(original_filename)[0]
        base_name = re.sub(r'[^\w\s-]', '', base_name).strip() or "AI_Audio"
        final_filename = f"{base_name}.mp3"
        final_path = os.path.join(OUTPUT_FOLDER, final_filename)
        
        counter = 1
        while os.path.exists(final_path):
             final_filename = f"{base_name}_{counter}.mp3"
             final_path = os.path.join(OUTPUT_FOLDER, final_filename)
             counter += 1
        
        with open(final_path, 'wb') as outfile:
            for chunk_path in valid_chunks:
                with open(chunk_path, 'rb') as infile:
                    outfile.write(infile.read())
        
        # Cleanup
        for f in valid_chunks:
            try: os.remove(f)
            except: pass
        try: os.rmdir(temp_dir)
        except: pass

        file_size = os.path.getsize(final_path)
        save_history({
            'id': task_id,
            'filename': original_filename,
            'audio_filename': final_filename,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'size': file_size,
            'engine': 'mixed' if fallback_triggered and engine == 'google' else engine
        })

        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['message'] = 'Conversion complete'
        tasks[task_id]['result'] = final_filename
        
    except Exception as e:
        logger.error(f"Error in task {task_id}: {e}")
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['message'] = str(e)

def run_async_process(task_id, file_path, original_filename, engine):
    asyncio.run(process_pdf_async(task_id, file_path, original_filename, engine))

# --- Routes ---

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400
    
    engine = request.form.get('engine', 'google')
    task_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, f"{task_id}_{filename}")
    file.save(file_path)
    
    tasks[task_id] = {'status': 'queued', 'progress': 0, 'message': 'Queued'}
    
    thread = threading.Thread(target=run_async_process, args=(task_id, file_path, file.filename, engine))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def get_status(task_id):
    return jsonify(tasks.get(task_id, {'status': 'not_found'}))

@app.route('/download/<task_id>')
def download_file(task_id):
    task = tasks.get(task_id)
    if not task or task['status'] != 'completed': return jsonify({'error': 'File not ready'}), 404
    return send_from_directory(OUTPUT_FOLDER, task['result'], as_attachment=True)

@app.route('/history')
def get_history():
    return jsonify(load_history())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
