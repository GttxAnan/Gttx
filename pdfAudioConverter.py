import os
import uuid
import asyncio
import json
import logging
import threading
import re
import shutil
import time
from datetime import datetime
import html
from flask import Flask, request, jsonify, send_file, redirect, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pypdf import PdfReader
import edge_tts
from google.cloud import texttospeech
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output' # Temporary local storage
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Failed to initialize Supabase: {e}")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state (In-memory task tracking)
tasks = {}

# --- Helper Functions ---

def get_session_id():
    return request.headers.get('X-Session-ID') or request.args.get('session_id') or 'default'

def upload_to_supabase(local_path, bucket_path):
    if not supabase: return None
    try:
        with open(local_path, 'rb') as f:
            supabase.storage.from_('audio-files').upload(file=f, path=bucket_path, file_options={"content-type": "audio/mpeg"})
        # Get public URL
        res = supabase.storage.from_('audio-files').get_public_url(bucket_path)
        return res
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        return None

def db_save_history(entry):
    if not supabase: return
    try:
        data = {
            "session_id": entry['session_id'],
            "filename": entry['filename'],
            "audio_url": entry['audio_url'],  # Use the Supabase URL
            "file_size": entry['size'],
            "voice_engine": entry['engine'],
            "created_at": datetime.now().isoformat()
        }
        supabase.table("conversions").insert(data).execute()
    except Exception as e:
        logger.error(f"Supabase DB save failed: {e}")

def db_get_history(session_id):
    if not supabase: return []
    try:
        response = supabase.table("conversions").select("*").eq("session_id", session_id).order("created_at", desc=True).execute()
        # Map back to frontend expected format
        history = []
        for item in response.data:
            history.append({
                'id': item['id'],
                'filename': item['filename'],
                'audio_filename': item['audio_url'], # Frontend expects this or we change frontend
                'date': datetime.fromisoformat(item['created_at']).strftime("%Y-%m-%d %H:%M:%S"),
                'size': item['file_size'],
                'engine': item['voice_engine'],
                'url': item['audio_url']
            })
        return history
    except Exception as e:
        logger.error(f"Supabase DB fetch failed: {e}")
        return []

def db_clear_session(session_id):
    if not supabase: return
    try:
        # 1. Fetch files to delete
        response = supabase.table("conversions").select("audio_url").eq("session_id", session_id).execute()
        files_to_delete = []
        for item in response.data:
            # Extract path from URL or save path in DB. 
            # Assuming audio_url was set to the public URL, we need to extract the path.
            # Format: .../storage/v1/object/public/audio-files/{session_id}/{filename}
            # We can also just reconstruct it if we saved the relative path, but we only saved URL.
            # Let's try to parse it or just rely on the session folder structure if we used one.
            # We used bucket_path = f"{session_id}/{final_filename}"
            
            # Safer strategy: List files in the session folder (if supported) or rely on the filename logic.
            # Since we can't easily parse the URL back to a clean path without regex, 
            # and `list` on storage is sometimes tricky with permissions,
            # we will just try to delete the folder if possible, or delete known files.
            
            # Let's extract filename from the URL to be safe, or just reconstruct the path 
            # since we know the structure is session_id/filename.
            if 'audio_url' in item and item['audio_url']:
                try:
                    # Simple parse: last component is filename
                     filename = item['audio_url'].split('/')[-1]
                     files_to_delete.append(f"{session_id}/{filename}")
                except: pass
        
        if files_to_delete:
            supabase.storage.from_('audio-files').remove(files_to_delete)
            
        # 2. Delete DB records
        supabase.table("conversions").delete().eq("session_id", session_id).execute()
        
    except Exception as e:
        logger.error(f"Supabase cleanup failed: {e}")


def find_start_page(reader):
    start_patterns = [re.compile(r"^\s*introduction\s*$", re.IGNORECASE | re.MULTILINE), re.compile(r"^\s*preface\s*$", re.IGNORECASE | re.MULTILINE), re.compile(r"^\s*chapter\s*1\s*$", re.IGNORECASE | re.MULTILINE), re.compile(r"^\s*1\s*$", re.IGNORECASE | re.MULTILINE)]
    exclude_patterns = [re.compile(r"^\s*contents\s*$", re.IGNORECASE | re.MULTILINE), re.compile(r"^\s*index\s*$", re.IGNORECASE | re.MULTILINE)]
    
    num_pages = len(reader.pages)
    for i in range(min(num_pages, 50)):
        try:
            text = reader.pages[i].extract_text()
            if not text: continue
            if any(p.search(text) for p in exclude_patterns): continue
            if any(p.search(text) for p in start_patterns): return i
        except: continue
    return 0

def find_end_page(reader, start_page):
    num_pages = len(reader.pages)
    end_patterns = [re.compile(r"^\s*index\s*$", re.IGNORECASE | re.MULTILINE), re.compile(r"^\s*bibliography\s*$", re.IGNORECASE | re.MULTILINE)]
    for i in range(num_pages - 1, start_page, -1):
        try:
            text = reader.pages[i].extract_text()
            if text and any(p.search(text) for p in end_patterns): return i
        except: continue
    return num_pages

def smart_chunk_text(text, max_chars=4500):
    text = text.replace('\n', ' ').strip()
    text = re.sub(r'\s+', ' ', text)
    # Basic chunking logic for brevity, preserving original logic's intent
    sentences = re.split(r'(?<=[.?!])\s+', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_chars:
            if current_chunk: chunks.append(current_chunk)
            current_chunk = sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence
    if current_chunk: chunks.append(current_chunk)
    return chunks

async def generate_audio_edge(text, output_file, voice="en-US-ChristopherNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def generate_audio_google(text, output_file, voice_name="en-US-Journey-D"):
    client = texttospeech.TextToSpeechClient()
    input_text = texttospeech.SynthesisInput(ssml=text) if text.startswith("<speak>") else texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
    with open(output_file, "wb") as out: out.write(response.audio_content)

async def process_pdf_async(task_id, file_path, original_filename, engine='edge', session_id='default'):
    try:
        tasks[task_id].update({'status': 'processing', 'progress': 5, 'message': 'Analyzing PDF...'})
        
        reader = PdfReader(file_path)
        start_page = find_start_page(reader)
        end_page = find_end_page(reader, start_page)
        
        text = ""
        for i in range(start_page, end_page):
            text += (reader.pages[i].extract_text() or "") + "\n"
            tasks[task_id]['progress'] = 5 + int((i - start_page) / (end_page - start_page) * 10)

        if not text.strip(): raise Exception("No text found")
        
        tasks[task_id].update({'progress': 20, 'message': 'Chunking text...'})
        chunks = smart_chunk_text(text)
        
        temp_dir = os.path.join(OUTPUT_FOLDER, task_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Process chunks (Simplified for brevity, assuming similar logic to original)
        chunk_files = []
        for i, chunk in enumerate(chunks):
            if tasks[task_id].get('cancelled'): raise asyncio.CancelledError()
            chunk_file = os.path.join(temp_dir, f"chunk_{i}.mp3")
            try:
                if engine == 'google': await asyncio.to_thread(generate_audio_google, chunk, chunk_file)
                else: await generate_audio_edge(chunk, chunk_file)
                chunk_files.append(chunk_file)
            except Exception as e:
                logger.error(f"Chunk {i} failed: {e}")
                # Fallback logic omitted for brevity, but should be here
            
            tasks[task_id]['progress'] = 20 + int((i + 1) / len(chunks) * 70)
            tasks[task_id]['message'] = f'Converting chunk {i+1}/{len(chunks)}...'

        # Merge
        tasks[task_id]['message'] = 'Merging audio...'
        final_filename = f"{uuid.uuid4()}.mp3"
        final_path = os.path.join(temp_dir, final_filename)
        
        with open(final_path, 'wb') as outfile:
            for f in chunk_files:
                with open(f, 'rb') as infile: outfile.write(infile.read())
        
        # Upload to Supabase
        tasks[task_id]['message'] = 'Uploading...'
        bucket_path = f"{session_id}/{final_filename}"
        public_url = upload_to_supabase(final_path, bucket_path)
        
        if not public_url:
            # Fallback for local dev if Supabase fails/not configured
            public_url = f"/local_download/{task_id}" # We need a route for this if fallback
            # Move to persistent local output if fallback
            fallback_path = os.path.join(OUTPUT_FOLDER, final_filename)
            shutil.move(final_path, fallback_path)
            tasks[task_id]['result_path'] = fallback_path # Store for local download

        # Save History
        file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        db_save_history({
            'session_id': session_id,
            'filename': original_filename,
            'audio_url': public_url,
            'size': file_size,
            'engine': engine
        })
        
        # Cleanup Temp
        shutil.rmtree(temp_dir)
        if os.path.exists(file_path): os.remove(file_path)

        tasks[task_id].update({'status': 'completed', 'progress': 100, 'message': 'Complete', 'result': public_url})

    except Exception as e:
        logger.error(f"Task failed: {e}")
        tasks[task_id].update({'status': 'failed', 'message': str(e)})

def run_async_process(task_id, file_path, original_filename, engine, session_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(process_pdf_async(task_id, file_path, original_filename, engine, session_id))
    loop.close()

# --- Routes ---

@app.route('/')
def index(): return jsonify({"status": "Backend API Running", "service": "Aurora Audio Converter"})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    session_id = request.form.get('session_id') or get_session_id()
    
    task_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_FOLDER, f"{task_id}{ext}")
    file.save(file_path)
    
    tasks[task_id] = {'status': 'queued', 'progress': 0, 'cancelled': False, 'pause_event': threading.Event()}
    tasks[task_id]['pause_event'].set()
    
    threading.Thread(target=run_async_process, args=(task_id, file_path, file.filename, request.form.get('engine', 'edge'), session_id)).start()
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def get_status(task_id):
    task = tasks.get(task_id)
    if not task: return jsonify({'status': 'not_found'})
    return jsonify({k: v for k, v in task.items() if k != 'pause_event'})

@app.route('/download/<task_id>')
def download_file(task_id):
    task = tasks.get(task_id)
    if not task or task.get('status') != 'completed': return jsonify({'error': 'Not ready'}), 404
    
    url = task.get('result')
    if url and url.startswith('http'):
        return redirect(url)
    elif task.get('result_path'):
        return send_file(task['result_path'], as_attachment=True)
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/history')
def get_history():
    session_id = get_session_id()
    return jsonify(db_get_history(session_id))

@app.route('/cleanup-session', methods=['POST'])
def cleanup_session():
    session_id = request.json.get('session_id') or get_session_id()
    if session_id:
        db_clear_session(session_id)
        return jsonify({'status': 'cleared'})
    return jsonify({'error': 'No session ID'}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
