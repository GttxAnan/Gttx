from flask import Flask, request, jsonify, send_file
from PyPDF2 import PdfReader
import os
from flask_cors import CORS
import logging
import io
from TTS.api import TTS

app = Flask(__name__)

# Configure upload and processed folders
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
PROCESSED_FOLDER = os.path.join(os.getcwd(), 'processed')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Enable CORS for the application
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('app.log')  # Log to file
    ]
)
logger = logging.getLogger(__name__)

# Initialize the Mozilla TTS engine
def init_tts_engine():
    return TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")

# Function to convert text to audio and return in-memory buffer
def text_to_audio_buffer(text):
    try:
        tts = init_tts_engine()
        audio_buffer = io.BytesIO()
        tts.tts_to_file(text=text, file_path=None, output_buffer=audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer
    except Exception as e:
        logger.error(f"Error during text-to-speech conversion: {e}")
        raise

@app.route('/upload', methods=['POST'])
def upload_pdf():
    logger.info('Received request for /upload')
    if 'file' not in request.files:
        logger.warning('No file part in the request')
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        logger.warning('No file selected')
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith('.pdf'):
        logger.warning(f'Invalid file type: {file.filename}')
        return jsonify({'error': 'Invalid file type. Only PDF allowed.'}), 400

    # Save the uploaded file
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    logger.info(f'File saved at {file_path}')

    try:
        # Extract text from the PDF
        logger.info(f'Extracting text from PDF: {file.filename}')
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()

        if not text.strip():
            logger.warning(f'No text found in the PDF: {file.filename}')
            return jsonify({'error': 'No text found in the PDF'}), 400

        # Convert text to audio buffer
        logger.info(f'Converting text to audio buffer for: {file.filename}')
        audio_buffer = text_to_audio_buffer(text)
        
        # Save the audio buffer to a file
        audio_file_name = file.filename.replace('.pdf', '.wav')
        audio_file_path = os.path.join(PROCESSED_FOLDER, audio_file_name)
        with open(audio_file_path, 'wb') as f:
            f.write(audio_buffer.getbuffer())

    except Exception as e:
        logger.error(f'Error during file processing: {e}')
        return jsonify({'error': f'Failed to process the file: {e}'}), 500

    logger.info(f'File processed successfully: {file.filename}')
    return jsonify({
        'message': 'File processed successfully',
        'audio_file': audio_file_name
    }), 200

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    logger.info(f'Received request to download: {filename}')
    file_path = os.path.join(PROCESSED_FOLDER, filename)
    if os.path.exists(file_path):
        logger.info(f'Sending file: {filename}')
        return send_file(file_path, as_attachment=False)
    logger.warning(f'File not found: {filename}')
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    logger.info('Starting the Flask application')
    app.run(debug=True)
