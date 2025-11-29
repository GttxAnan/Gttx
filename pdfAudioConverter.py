from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader
import os
from flask_cors import CORS
import logging
import threading
import uuid
import asyncio
import edge_tts
import json
from datetime import datetime
import re

app = Flask(__name__, static_folder='static', template_folder='templates')

# Change Jinja2 delimiters to avoid conflict with React
app.jinja_env.variable_start_string = '(('
app.jinja_env.variable_end_string = '))'
app.jinja_env.block_start_string = '(%'
app.jinja_env.block_end_string = '%)'
app.jinja_env.comment_start_string = '(#'
app.jinja_env.comment_end_string = '#)'

# Configure folders
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
PROCESSED_FOLDER = os.path.join(os.getcwd(), 'processed')
HISTORY_FILE = os.path.join(os.getcwd(), 'history.json')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Enable CORS
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Global dictionary to store task status
tasks = {}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_to_history(metadata):
    history = load_history()
    history.insert(0, metadata)  # Add to beginning
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def find_start_page(reader):
    """
    Finds the starting page based on regex patterns.
    Returns the page index (0-based).
    """
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
                        logger.info(f'Found start pattern at page {i}')
                        return i
        except Exception:
            continue
            
    return 0

async def generate_audio_chunk_with_retry(text, output_path, voice="en-US-AriaNeural", max_retries=3):
    """
    Generates audio for a single chunk with retry logic for API limits.
    """
    if not text.strip():
        return False
        
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                logger.warning(f"TTS failed for chunk (attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s. Error: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"TTS failed permanently for chunk after {max_retries} attempts. Error: {e}")
                raise e
    return False

def smart_chunk_text(text, max_chars=2000):
    """
    Splits text into chunks respecting sentence boundaries.
    """
    chunks = []
    current_chunk = ""
    
    # Split by sentence endings roughly
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_chars:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            
            # Handle extremely long sentences (rare but possible)
            while len(current_chunk) > max_chars:
                chunks.append(current_chunk[:max_chars])
                current_chunk = current_chunk[max_chars:]
                
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

async def process_pdf_async(task_id, file_path, original_filename):
    try:
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 5
        tasks[task_id]['message'] = 'Analyzing PDF structure...'
        
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        start_page_index = find_start_page(reader)
        
        tasks[task_id]['message'] = f'Extracting text (starting page {start_page_index + 1})...'
        
        # Extract all text first
        full_text = ""
        for i in range(start_page_index, total_pages):
            text = reader.pages[i].extract_text()
            if text:
                full_text += text + "\n\n"
            
            # Update progress for extraction (5% to 15%)
            if i % 10 == 0:
                progress = 5 + int(((i - start_page_index) / (total_pages - start_page_index)) * 10)
                tasks[task_id]['progress'] = progress

        if not full_text.strip():
            raise Exception("No text found in PDF")

        tasks[task_id]['progress'] = 15
        tasks[task_id]['message'] = 'Optimizing text chunks...'

        # Smart chunking
        text_chunks = smart_chunk_text(full_text)
        
        tasks[task_id]['progress'] = 20
        tasks[task_id]['message'] = f'Converting {len(text_chunks)} chunks to audio...'
        
        # Create temporary directory for chunks
        temp_dir = os.path.join(PROCESSED_FOLDER, task_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Semaphore to limit concurrency (prevent 429s)
        # Increased to 10 because we have retry logic now
        semaphore = asyncio.Semaphore(10) 

        async def process_chunk(index, text):
            async with semaphore:
                chunk_filename = os.path.join(temp_dir, f"chunk_{index:04d}.mp3") # Pad index for sorting
                await generate_audio_chunk_with_retry(text, chunk_filename)
                return chunk_filename

        # Create tasks for all chunks
        chunk_tasks = [process_chunk(i, text) for i, text in enumerate(text_chunks)]
        
        # Run tasks and track progress
        completed = 0
        total_chunks = len(chunk_tasks)
        
        for future in asyncio.as_completed(chunk_tasks):
            await future
            completed += 1
            # Progress from 20% to 90%
            progress = 20 + int((completed / total_chunks) * 70)
            tasks[task_id]['progress'] = progress
            tasks[task_id]['message'] = f'Converted chunk {completed}/{total_chunks}...'

        # Collect ordered filenames
        ordered_chunk_files = [os.path.join(temp_dir, f"chunk_{i:04d}.mp3") for i in range(len(text_chunks))]
        valid_chunks = [f for f in ordered_chunk_files if os.path.exists(f)]

        tasks[task_id]['message'] = 'Merging audio files...'
        
        # Merge chunks
        final_filename = f"{uuid.uuid4()}.mp3"
        final_path = os.path.join(PROCESSED_FOLDER, final_filename)
        
        with open(final_path, 'wb') as outfile:
            for chunk_path in valid_chunks:
                with open(chunk_path, 'rb') as infile:
                    outfile.write(infile.read())
        
        # Cleanup temp chunks
        for f in valid_chunks:
            try:
                os.remove(f)
            except:
                pass
        try:
            os.rmdir(temp_dir)
        except:
            pass

        # Save history
        file_size = os.path.getsize(final_path)
        metadata = {
            'id': task_id,
            'filename': original_filename,
            'audio_filename': final_filename,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'size': file_size,
            'pages': total_pages - start_page_index
        }
        save_to_history(metadata)

        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['message'] = 'Conversion complete'
        tasks[task_id]['filename'] = final_filename
        
    except Exception as e:
        logger.error(f"Error in task {task_id}: {e}")
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['message'] = str(e)

def run_async_process(task_id, file_path, original_filename):
    asyncio.run(process_pdf_async(task_id, file_path, original_filename))

@app.route('/')
def index():
    return send_file('templates/index.html')

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.endswith('.pdf'):
        return jsonify({'error': 'Invalid file type'}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        'status': 'queued',
        'progress': 0,
        'message': 'Queued for processing',
        'filename': None
    }

    thread = threading.Thread(target=run_async_process, args=(task_id, file_path, file.filename))
    thread.start()

    return jsonify({'task_id': task_id, 'message': 'Processing started'}), 202

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@app.route('/download/<task_id>', methods=['GET'])
def download_file(task_id):
    # Check active tasks first
    task = tasks.get(task_id)
    if task and task.get('filename'):
        file_path = os.path.join(PROCESSED_FOLDER, task['filename'])
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=f"audiobook_{task_id[:8]}.mp3")

    # Check history if not in active tasks (for re-downloads)
    history = load_history()
    for item in history:
        if item['id'] == task_id:
             file_path = os.path.join(PROCESSED_FOLDER, item['audio_filename'])
             if os.path.exists(file_path):
                 return send_file(file_path, as_attachment=True, download_name=f"audiobook_{item['filename']}.mp3")
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/history', methods=['GET'])
def get_history():
    return jsonify(load_history())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
