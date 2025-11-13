import os
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from db_models import db, HTRResult
from data_models import HTRSchema, ExtractedField
from pydantic import ValidationError
import json
import fitz  # PyMuPDF
from PIL import Image
import io
import google.generativeai as genai
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:root@localhost:5432/aura_db'  # <-- UPDATE THIS with your actual PostgreSQL password
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def convert_file_to_image_bytes(file_bytes, mime_type):
    """
    Converts the first page of a PDF to a JPEG image, or passes through other image types.
    Returns the image bytes and the new mime type.
    """
    if mime_type == 'application/pdf':
        try:
            # Open the PDF from bytes
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            # Get the first page
            page = pdf_document.load_page(0)
            # Render page to a pixmap (an image)
            pix = page.get_pixmap(dpi=200) # Higher DPI for better quality
            # Convert pixmap to a PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            # Save the PIL image to a byte stream
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            pdf_document.close()
            return img_byte_arr.getvalue(), 'image/jpeg'
        except Exception as e:
            raise ValueError(f"Failed to convert PDF to image: {e}")
    # If it's already an image, just return the original bytes
    return file_bytes, mime_type

 # Gemini extraction logic for images
def gemini_extract(image_bytes, prompt, mime_type='image/jpeg', model_name='gemini-2.5-flash'):
    """
    Extracts text from an image using the Gemini Pro Vision model.
    """
    # --- API Key Configuration ---
    # IMPORTANT: For production, it is much safer to use environment variables.
    # 1. Best Practice: Use an environment variable (see instructions below).
    # 2. Quick Test (Less Secure): Hardcode your key directly.
    api_key = "AIzaSyCADmP2lF_-0A3IGCiBmXPogiFlkFg-h1I"  # <-- UPDATED KEY (Ensure this is your valid key)
    if "YOUR_API_KEY_HERE" in api_key:
        print("WARNING: Using a hardcoded API key. Set the GEMINI_API_KEY environment variable for better security.")
    genai.configure(api_key=api_key)

    # Use the supported Gemini model for image analysis
    model = genai.GenerativeModel(model_name)

    # The vision model expects a list of content parts
    image_part = {
        "mime_type": mime_type,
        "data": image_bytes
    }

    try:
        response = model.generate_content([prompt, image_part])
        # Clean up the response text to extract only the JSON part
        extracted_json = json.loads(response.text)
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback: if the response is not clean JSON, try to find it within the text
        import re
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            extracted_json = json.loads(match.group(0))
        else:
            raise ValueError(f"Failed to parse JSON from Gemini response. Raw response: {response.text}") from e
            
    return extracted_json

def list_gemini_models():
    """Lists available Gemini models and their capabilities."""
    api_key = os.environ.get("GEMINI_API_KEY") or "AIzaSyCADmP2lF_-0A3IGCiBmXPogiFlkFg-h1I" # <-- UPDATED KEY
    if api_key == "PASTE_YOUR_REAL_GEMINI_API_KEY_HERE":
        print("WARNING: GEMINI_API_KEY not set. Cannot list models.")
        return
    genai.configure(api_key=api_key)
    print("\n--- Listing Available Gemini Models ---")
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"  Model: {m.name}")
            print(f"    Description: {m.description}")
            print(f"    Input Modalities: {m.input_token_limit}") # This often implies modalities
            print(f"    Supported Methods: {m.supported_generation_methods}")
            print("-" * 30)
    print("--- End Model List ---\n")

@app.cli.command('init-db')
def init_db():
    """Initialize the database tables."""
    with app.app_context():
        db.create_all()
        print('Database initialized.')

@app.route('/extract_dual_source', methods=['POST'])
def extract_dual_source():
    # Phase 1: Input Handling
    if 'mandate_file' not in request.files or 'id_file' not in request.files or 'document_id' not in request.form:
        return jsonify({"error": "Missing required files or document_id"}), 400
    document_id = request.form['document_id']
    mandate_file = request.files['mandate_file']
    id_file = request.files['id_file']

    try:
        mandate_bytes = mandate_file.read()
        id_bytes = id_file.read()
    except Exception as e:
        return jsonify({"error": "Failed to read file bytes", "details": str(e)}), 400


    # Phase 2: Extraction Logic with accuracy-focused prompts
    mandate_prompt = (
        "Extract the following fields from the Mandate Card: SURNAME, NAME, OCCUPATION, GROSS MONTHLY INCOME, CURRENT EMPLOYER, EMPLOYER ADDRESS. "
        "GROSS MONTHLY INCOME must be a clean number (float) stripped of all currency symbols and text. "
        "For names, occupation, employer, and address, if the handwritten text contains common HTR errors, apply contextual correction to infer the correct word. "
        "If a value for a field cannot be determined, return null for its 'extracted_value'. "
        "Return the result as a JSON object containing a single key 'fields', which is a list of objects. Each object in the list must have keys: 'field_name' and 'extracted_value'."
        "Do not include the source type in the response."
    )

    try:
        # Assuming PDF files are sent, we need to handle them. For now, let's assume they are images.
        # A real implementation would convert PDF pages to images first.
        mandate_image_bytes, mandate_image_mime = convert_file_to_image_bytes(mandate_bytes, mandate_file.mimetype)
        if not mandate_image_bytes:
            return jsonify({"error": "Failed to process Mandate Card file."}), 400

        # Extraction for Mandate Card
        mandate_raw = gemini_extract(mandate_image_bytes, mandate_prompt, mandate_image_mime)

        # --- CRITICAL FIX: PAUSE HERE to respect the Free Tier's RPM limit ---
        print("INFO: Pausing for 60 seconds to respect API rate limits...")
        time.sleep(60) # Increased pause to 60 seconds for the free tier
        # --- DEBUGGING: Log the raw response from Gemini ---
        print(f"DEBUG: Raw Gemini response for Mandate Card: {json.dumps(mandate_raw, indent=2)}")

        # --- POST-PROCESSING: Ensure all required keys and types for Pydantic validation ---
        for field in mandate_raw.get('fields', []):
            # Ensure extracted_value is a string
            if 'extracted_value' in field and field['extracted_value'] is not None:
                field['extracted_value'] = str(field['extracted_value'])
            # Add missing keys with defaults
            if 'corrected_value' not in field:
                field['corrected_value'] = None
            if 'confidence_score' not in field:
                field['confidence_score'] = 0.99
            if 'is_corrected' not in field:
                field['is_corrected'] = False

        mandate_raw['document_id'] = document_id
        mandate_raw['source_type'] = 'MANDATE_CARD'
        mandate_schema = HTRSchema(**mandate_raw)
    except (ValidationError, ValueError) as e:
        error_details = e.errors() if isinstance(e, ValidationError) else str(e)
        print(f"ERROR: Mandate Card validation failed. Details: {error_details}") # Add server-side logging
        return jsonify({"error": "Mandate Card extraction or validation failed", "details": error_details}), 422

    # National ID extraction enabled
    id_prompt = (
        "Extract the following fields from the National ID: ID_NUMBER, DATE_OF_BIRTH, GENDER, NATIONALITY, PLACE OF BIRTH, FULL NAME, ISSUE DATE. "
        "DATE_OF_BIRTH must be strictly in YYYY-MM-DD format. "
        "GENDER must be strictly 'MALE', 'FEMALE', or the equivalent in the document's language. "
        "ID_NUMBER must be a clean string containing only alphanumeric characters and hyphens. "
        "If a value for a field cannot be determined, return null for its 'extracted_value'. "
        "Return the result as a JSON object containing a single key 'fields', which is a list of objects. Each object in the list must have keys: 'field_name' and 'extracted_value'."
        "Do not include the source type in the response."
    )
    try:
        id_image_bytes, id_image_mime = convert_file_to_image_bytes(id_bytes, id_file.mimetype)
        if not id_image_bytes:
            return jsonify({"error": "Failed to process National ID file."}), 400

        id_raw = gemini_extract(id_image_bytes, id_prompt, id_image_mime)
        print(f"DEBUG: Raw Gemini response for National ID: {json.dumps(id_raw, indent=2)}")

        # --- POST-PROCESSING: Ensure all required keys and types for Pydantic validation ---
        for field in id_raw.get('fields', []):
            if 'extracted_value' in field and field['extracted_value'] is not None:
                field['extracted_value'] = str(field['extracted_value'])
            if 'corrected_value' not in field:
                field['corrected_value'] = None
            if 'confidence_score' not in field:
                field['confidence_score'] = 0.99
            if 'is_corrected' not in field:
                field['is_corrected'] = False

        id_raw['document_id'] = document_id
        id_raw['source_type'] = 'ID_CARD'
        id_schema = HTRSchema(**id_raw)
    except (ValidationError, ValueError) as e:
        error_details = e.errors() if isinstance(e, ValidationError) else str(e)
        print(f"ERROR: National ID validation failed. Details: {error_details}") # Add server-side logging
        return jsonify({"error": "National ID extraction or validation failed", "details": error_details}), 422


    # Phase 3: Database Storage
    with app.app_context():
        # Upsert Mandate Card fields
        for field in mandate_schema.fields:
            existing = HTRResult.query.filter_by(
                document_id=document_id,
                source_type=mandate_schema.source_type,
                field_name=field.field_name
            ).first()
            if existing:
                existing.extracted_value = field.extracted_value
                existing.confidence_score = field.confidence_score
                existing.is_corrected = field.is_corrected
                existing.corrected_value = field.corrected_value
                db.session.add(existing)
            else:
                result = HTRResult(
                    document_id=document_id,
                    source_type=mandate_schema.source_type,
                    field_name=field.field_name,
                    extracted_value=field.extracted_value,
                    confidence_score=field.confidence_score,
                    is_corrected=field.is_corrected,
                    corrected_value=field.corrected_value
                )
                db.session.add(result)
        # Upsert National ID fields
        for field in id_schema.fields:
            existing = HTRResult.query.filter_by(
                document_id=document_id,
                source_type=id_schema.source_type,
                field_name=field.field_name
            ).first()
            if existing:
                existing.extracted_value = field.extracted_value
                existing.confidence_score = field.confidence_score
                existing.is_corrected = field.is_corrected
                existing.corrected_value = field.corrected_value
                db.session.add(existing)
            else:
                result = HTRResult(
                    document_id=document_id,
                    source_type=id_schema.source_type,
                    field_name=field.field_name,
                    extracted_value=field.extracted_value,
                    confidence_score=field.confidence_score,
                    is_corrected=field.is_corrected,
                    corrected_value=field.corrected_value
                )
                db.session.add(result)
        db.session.commit()

    # Phase 4: Final Output
    # Map Mandate Card fields to expected frontend keys
    mandate_fields = {
        "profession": None,
        "employment_status": None,
        "monthly_salary": None,
        "employer_address": None,
        "current_employer": None
    }
    for f in mandate_schema.fields:
        key = f.field_name.lower().replace(' ', '_')
        if key in mandate_fields:
            mandate_fields[key] = f.extracted_value
        # Support alternate field names
        if key == "gross_monthly_income":
            mandate_fields["monthly_salary"] = f.extracted_value
        if key == "occupation":
            mandate_fields["profession"] = f.extracted_value
        if key == "employer_address":
            mandate_fields["employer_address"] = f.extracted_value
        if key == "employer_name" or key == "current_employer":
            mandate_fields["current_employer"] = f.extracted_value
        if key == "employment_status":
            mandate_fields["employment_status"] = f.extracted_value

    # Map ID Card fields to expected frontend keys
    id_fields = {
        "full_name": None,
        "id_number": None,
        "date_of_birth": None,
        "gender": None,
        "nationality": None,
        "issue_date": None,
        "place_of_birth": None
    }
    for f in id_schema.fields:
        key = f.field_name.lower().replace(' ', '_')
        if key in id_fields:
            id_fields[key] = f.extracted_value

    response = {
        "document_id": document_id,
        "mandate_card": mandate_fields,
        "national_id": id_fields
    }
    return jsonify(response), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    list_gemini_models() # Call this to list models on startup
    app.run(port=5001, debug=True)
