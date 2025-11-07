import os
from flask import Flask, request, jsonify
from db_models import db, HTRResult
from data_models import HTRSchema, ExtractedField
from pydantic import ValidationError
import json
from google.generativeai import GenerativeModel
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:your_password@localhost:5432/aura_db'  # Update credentials
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Dummy Gemini extraction logic (replace with real API call)
def gemini_extract(image_bytes, prompt):
    genai.configure(api_key="AIzaSyAMBaG7hKhyNwEsMz_PaKkh5EV0yJN8ESE")  # Replace with your actual Gemini API key
    model = GenerativeModel('gemini-pro')
    response = model.generate_content(prompt, image=image_bytes)
    # Parse the response to get the JSON output
    # Gemini may return a string, so parse it to dict
    try:
        extracted_json = json.loads(response.text)
    except Exception:
        # Fallback: try to extract JSON from text
        import re
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            extracted_json = json.loads(match.group(0))
        else:
            extracted_json = {"fields": []}
    return extracted_json

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
    mandate_bytes = mandate_file.read()
    id_bytes = id_file.read()

    # Phase 2: Extraction Logic with accuracy-focused prompts
    mandate_prompt = (
        "Extract the following fields from the Mandate Card: SURNAME, NAME, OCCUPATION, GROSS MONTHLY INCOME. "
        "GROSS MONTHLY INCOME must be a clean number (float or string) stripped of all currency symbols and text. "
        "For names and occupation, if the handwritten text contains common HTR errors (e.g., '7' instead of 'T'), apply contextual correction to infer the correct word. "
        "Return the result as a JSON object with keys: 'field_name' and 'extracted_value'."
        "Source type must be 'MANDATE_CARD'."
    )
    mandate_raw = gemini_extract(mandate_bytes, mandate_prompt)
    mandate_raw['document_id'] = document_id
    mandate_raw['source_type'] = 'MANDATE_CARD'
    try:
        mandate_schema = HTRSchema(**mandate_raw)
    except ValidationError as e:
        return jsonify({"error": "Mandate Card validation failed", "details": e.errors()}), 422

    id_prompt = (
        "Extract the following fields from the National ID: ID_NUMBER, DATE_OF_BIRTH, GENDER, NATIONALITY. "
        "DATE_OF_BIRTH must be strictly in YYYY-MM-DD format. "
        "GENDER must be strictly 'MALE' or 'FEMALE'. "
        "ID_NUMBER must be a clean string containing only digits and hyphens. "
        "Return the result as a JSON object with keys: 'field_name' and 'extracted_value'."
        "Source type must be 'NATIONAL_ID'."
    )
    id_raw = gemini_extract(id_bytes, id_prompt)
    id_raw['document_id'] = document_id
    id_raw['source_type'] = 'NATIONAL_ID'
    try:
        id_schema = HTRSchema(**id_raw)
    except ValidationError as e:
        return jsonify({"error": "National ID validation failed", "details": e.errors()}), 422

    # Phase 3: Database Storage
    with app.app_context():
        for schema in [mandate_schema, id_schema]:
            for field in schema.fields:
                result = HTRResult(
                    document_id=document_id,
                    source_type=schema.source_type,
                    field_name=field.field_name,
                    extracted_value=field.extracted_value,
                    confidence_score=field.confidence_score,
                    is_corrected=field.is_corrected,
                    corrected_value=field.corrected_value
                )
                db.session.add(result)
        db.session.commit()

    # Phase 4: Final Output
    response = {
        "document_id": document_id,
        "mandate_card": [f.dict() for f in mandate_schema.fields],
        "national_id": [f.dict() for f in id_schema.fields]
    }
    return jsonify(response), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
