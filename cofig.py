import os

class Config:
    # Security and Base App Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'aura-secret-key-2024'
    
    # File Upload Configuration
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    
    # Database Configuration (add if needed)
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///aura_db.sqlite'
    # SQLALCHEMY_TRACK_MODIFICATIONS = False