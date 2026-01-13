import os
import uuid
import asyncio
import json
import math
import logging
import threading
import re
from datetime import datetime
import html
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
    start_patterns = [
        re.compile(r"^\s*introduction\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*preface\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*chapter\s*1\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*chapter\s*one\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*1\s*$", re.IGNORECASE | re.MULTILINE)
    ]
    
    exclude_patterns = [
        re.compile(r"^\s*contents\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*table\s*of\s*contents\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*list\s*of\s*tables\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*list\s*of\s*figures\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*index\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*acknowledgments\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*forward\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*dedicated\s*to\s*$", re.IGNORECASE | re.MULTILINE)
    ]

    num_pages = len(reader.pages)
    check_limit = min(num_pages, 50)
    
    for i in range(check_limit):
        try:
            text = reader.pages[i].extract_text()
            if not text: continue
            
            is_excluded = False
            for pattern in exclude_patterns:
                if pattern.search(text):
                    is_excluded = True
                    break
            
            if is_excluded:
                continue

            for pattern in start_patterns:
                if pattern.search(text):
                    return i
        except: continue
        
    return 0

def find_end_page(reader, start_page):
    num_pages = len(reader.pages)
    end_patterns = [
        re.compile(r"^\s*index\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*bibliography\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*notes\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*acknowledgments\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*thank\s*you\s*$", re.IGNORECASE | re.MULTILINE)
    ]
    
    # Check from the end backwards
    for i in range(num_pages - 1, start_page, -1):
        try:
            text = reader.pages[i].extract_text()
            if text:
                for pattern in end_patterns:
                    if pattern.search(text):
                        return i
        except: continue
    return num_pages

def smart_chunk_text(text, max_chars=4500):
    # Pre-process: Replace newlines with spaces to treat text as a continuous stream
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Detect headings and insert SSML break
    text = html.escape(text)
    
    heading_patterns = [
        r'(?i)\b(chapter\s+\d+|introduction|part\s+[IVX]+|prologue|epilogue)\b'
    ]
    
    for pattern in heading_patterns:
        text = re.sub(pattern, r'\1 <break time="2000ms"/>', text)

    chunks = []
    current_chunk = ""
    
    # Split by sentence endings (. ? !). We keep the punctuation.
    sentences = re.split(r'(?<=[.?!])\s+', text)
    
    for sentence in sentences:
        if not sentence.strip(): continue # Skip empty sentences

        # If a single sentence is too long...
        if len(sentence) > max_chars:
            parts = sentence.split(', ')
            for part in parts:
                if len(current_chunk) + len(part) + 2 > max_chars:
                    if current_chunk.strip():
                        chunks.append(f"<speak>{current_chunk.strip()}</speak>")
                        current_chunk = ""
                    if len(part) > max_chars:
                         chunks.append(f"<speak>{part.strip()}</speak>")
                    else:
                         current_chunk = part
                else:
                    current_chunk += (", " if current_chunk and not current_chunk.endswith(' ') else "") + part
        
        elif len(current_chunk) + len(sentence) + 1 > max_chars:
            if current_chunk.strip():
                chunks.append(f"<speak>{current_chunk.strip()}</speak>")
            current_chunk = sentence
        else:
            current_chunk += (" " if current_chunk else "") + sentence

    if current_chunk.strip():
        chunks.append(f"<speak>{current_chunk.strip()}</speak>")
    
    return chunks


async def generate_audio_edge(text, output_file, voice="en-US-ChristopherNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def generate_audio_google(text, output_file, voice_name="en-US-Journey-D"):
    client = texttospeech.TextToSpeechClient()
    
    if text.startswith("<speak>"):
        input_text = texttospeech.SynthesisInput(ssml=text)
    else:
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
        
        # Check for cancellation
        if tasks[task_id].get('cancelled'):
             raise Exception("Task cancelled by user")
        
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        start_page_index = find_start_page(reader)
        end_page_index = find_end_page(reader, start_page_index)
        
        tasks[task_id]['message'] = f'Extracting text (pages {start_page_index + 1}-{end_page_index})...'
        full_text = ""
        for i in range(start_page_index, end_page_index):
            text = reader.pages[i].extract_text()
            if text: full_text += text + "\n\n"
            if i % 10 == 0:
                tasks[task_id]['progress'] = 5 + int(((i - start_page_index) / (end_page_index - start_page_index)) * 10)

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

        async def process_chunk_controlled(index, text):
            nonlocal fallback_triggered
            
            # Initial check (fast fail)
            if tasks[task_id].get('cancelled'): 
                logger.info(f"Task {task_id}: Cancelled before chunk {index}")
                raise asyncio.CancelledError()

            async with semaphore:
                # Check pause INSIDE semaphore to prevent race condition where task passed outer check but waited on semaphore
                while not tasks[task_id]['pause_event'].is_set():
                    if tasks[task_id].get('cancelled'): 
                        logger.info(f"Task {task_id}: Cancelled while paused at chunk {index}")
                        raise asyncio.CancelledError()
                    
                    if tasks[task_id]['status'] != 'paused':
                        logger.info(f"Task {task_id}: Pausing at chunk {index}")
                        tasks[task_id]['status'] = 'paused'
                    
                    await asyncio.sleep(1)
                
                # Restore status if we were paused
                if tasks[task_id]['status'] == 'paused':
                     logger.info(f"Task {task_id}: Resuming at chunk {index}")
                     tasks[task_id]['status'] = 'processing'

                if tasks[task_id].get('cancelled'): raise asyncio.CancelledError()

                chunk_filename = os.path.join(temp_dir, f"chunk_{index:04d}.mp3")
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if engine == 'google' and not fallback_triggered:
                            try:
                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(None, generate_audio_google, text, chunk_filename)
                                return chunk_filename
                            except Exception as e:
                                logger.warning(f"Task {task_id}: Google TTS error on chunk {index} (Attempt {attempt+1}/{max_retries}): {e}. Falling back.")
                                if attempt == max_retries - 1:
                                    fallback_triggered = True
                                else:
                                    await asyncio.sleep(1 * (attempt + 1))
                                    continue
                        
                        # Edge TTS with Fallback
                        try:
                            await generate_audio_edge(text, chunk_filename)
                            return chunk_filename
                        except Exception as e:
                            logger.error(f"Task {task_id}: Edge TTS failed on chunk {index}: {e}")
                            raise Exception("Service unavailable at moment")

                    except Exception as e:
                        logger.error(f"Task {task_id}: Failed to process chunk {index} (Attempt {attempt+1}/{max_retries}): {e}. Text snippet: {text[:50]}...")
                        if attempt == max_retries - 1:
                            logger.error(f"Task {task_id}: Skipping chunk {index} after max retries.")
                            return None 
                        await asyncio.sleep(1 * (attempt + 1))

        chunk_tasks = [process_chunk_controlled(i, text) for i, text in enumerate(text_chunks)]
        completed = 0
        total_chunks = len(chunk_tasks)
        
        logger.info(f"Task {task_id}: Started processing {total_chunks} chunks")
        
        for future in asyncio.as_completed(chunk_tasks):
            await future
            completed += 1
            tasks[task_id]['progress'] = 20 + int((completed / total_chunks) * 70)
            msg = f'Converted chunk {completed}/{total_chunks}...'
            if fallback_triggered: msg += " (Standard Voice)"
            tasks[task_id]['message'] = msg
            # logger.info(f"Task {task_id}: {msg}")

        ordered_chunk_files = [os.path.join(temp_dir, f"chunk_{i:04d}.mp3") for i in range(len(text_chunks))]
        valid_chunks = [f for f in ordered_chunk_files if os.path.exists(f)]

        tasks[task_id]['message'] = 'Merging audio files...'
        logger.info(f"Task {task_id}: Merging {len(valid_chunks)} audio files")
        
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
        logger.info(f"Task {task_id}: Completed successfully. Saved to {final_filename}")
        
    except asyncio.CancelledError:
        logger.info(f"Task {task_id}: Process cancelled by user")
        tasks[task_id]['status'] = 'cancelled'
        tasks[task_id]['message'] = 'Cancelled'
        # Cleanup
        try:
             import shutil
             if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        except: pass

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
    
    tasks[task_id] = {
        'status': 'queued', 
        'progress': 0, 
        'message': 'Queued',
        'pause_event': threading.Event(),
        'cancelled': False
    }
    tasks[task_id]['pause_event'].set() # Start as running
    
    thread = threading.Thread(target=run_async_process, args=(task_id, file_path, file.filename, engine))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def get_status(task_id):
    status_data = tasks.get(task_id, {'status': 'not_found'})
    # Convert event to boolean for JSON
    if 'pause_event' in status_data:
        status_data_copy = status_data.copy()
        del status_data_copy['pause_event']
        return jsonify(status_data_copy)
    return jsonify(status_data)

@app.route('/pause/<task_id>', methods=['POST'])
def pause_task(task_id):
    if task_id in tasks:
        tasks[task_id]['pause_event'].clear()
        tasks[task_id]['status'] = 'paused'
        return jsonify({'status': 'paused'})
    return jsonify({'error': 'Task not found'}), 404

@app.route('/resume/<task_id>', methods=['POST'])
def resume_task(task_id):
    if task_id in tasks:
        tasks[task_id]['pause_event'].set()
        tasks[task_id]['status'] = 'processing'
        return jsonify({'status': 'resumed'})
    return jsonify({'error': 'Task not found'}), 404

@app.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id):
    if task_id in tasks:
        tasks[task_id]['cancelled'] = True
        tasks[task_id]['pause_event'].set() # Unblock if paused
        return jsonify({'status': 'cancelled'})
    return jsonify({'error': 'Task not found'}), 404

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
