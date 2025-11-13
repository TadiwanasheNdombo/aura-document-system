# Aura Document System

## Overview
Aura Document System is a web-based platform for automated extraction and management of document data using AI (Google Gemini), Flask, SQLAlchemy, and a modern frontend. It supports dual-source extraction from Mandate Cards and National IDs, auto-populates forms, and persists results in a PostgreSQL database.

## Features
- Upload and process Mandate Card and National ID documents
- AI-powered extraction using Gemini
- Auto-populate frontend forms with extracted data
- Store results in PostgreSQL
- Upsert logic to prevent duplicate database entries
- User-friendly dashboard and document navigation

## Setup Instructions
1. **Clone the repository**
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure PostgreSQL**:
   - Create a database named `aura_db`
   - Update credentials in `app.py` and `app_dual_extraction.py`
4. **Set Gemini API Key**:
   - Add your key in `app_dual_extraction.py` or use environment variable `GEMINI_API_KEY`
5. **Run the Flask app**:
   ```bash
   python app.py
   python app_dual_extraction.py
   ```
6. **Access the frontend**:
   - Open `http://127.0.0.1:5000` (main app)
   - Extraction service runs on `http://127.0.0.1:5001`

## Architecture
- **Backend**: Flask, SQLAlchemy, Gemini API
- **Frontend**: HTML, Bootstrap, JavaScript
- **Database**: PostgreSQL

## API Endpoints
### `/extract_dual_source` (POST)
- **Description**: Extracts fields from Mandate Card and National ID
- **Request**: Multipart form with `mandate_file`, `id_file`, `document_id`
- **Response**:
  ```json
  {
    "document_id": "...",
    "mandate_card": { ...fields... },
    "national_id": { ...fields... }
  }
  ```

## Database Schema
- **Table**: `htr_extracted_data`
  - `document_id`, `source_type`, `field_name`, `extracted_value`, `confidence_score`, `is_corrected`, `corrected_value`, timestamps
  - Unique constraint: (`document_id`, `source_type`, `field_name`)

## Frontend Workflow
- User selects documents and triggers auto-fetch
- JS sends files to `/extract_dual_source`
- Extracted fields are mapped and populated in forms

## Troubleshooting
- **API Key errors**: Ensure valid Gemini key
- **Database errors**: Check connection string and table schema
- **Extraction errors**: Review logs for validation or parsing issues

## Contributing
- Fork the repo and submit pull requests
- Follow PEP8 and best practices
- Document new features in this README

## License
MIT

---
For more details, see code comments and individual module docstrings.
