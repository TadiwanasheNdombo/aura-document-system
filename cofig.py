import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'aura-secret-key-2024'
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    
    # Tesseract OCR configuration (if needed)
    TESSERACT_CMD = '/usr/bin/tesseract'  # Path may vary by system
    
    # Poppler path for PDF to image conversion (if needed)
    POPPLER_PATH = None  # Set if poppler is not in system PATH
