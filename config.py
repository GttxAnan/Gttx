import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get folder paths from the environment or use defaults
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', './uploads')
PROCESSED_FOLDER = os.getenv('PROCESSED_FOLDER', './processed')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

print(f"UPLOAD_FOLDER: {UPLOAD_FOLDER}")
print(f"PROCESSED_FOLDER: {PROCESSED_FOLDER}")
