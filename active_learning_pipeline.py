from flask import Flask, request, jsonify
from pydantic import BaseModel, ValidationError, Field
from google.generativeai import GenerativeModel
import base64
import os
from models import db, DocumentExtraction

app = Flask(__name__)
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:root@localhost:5432/aura_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Pydantic schema for validation
class ExtractedFields(BaseModel):
    surname: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    occupation: str = Field(..., min_length=1)
    gross_monthly_income: float

# Gemini extraction logic (stub/prototype)
def extract_fields_with_gemini(image_bytes):
    # Convert image to base64 for Gemini API
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    prompt = (
        "Extract the following fields from the document image: "
        "SURNAME, NAME, OCCUPATION, GROSS MONTHLY INCOME. "
        "Return the result strictly as a JSON object with keys: 'surname', 'name', 'occupation', 'gross_monthly_income'."
    )
    # Replace with actual Gemini API call
    # model = GenerativeModel('gemini-pro')
    # response = model.generate_content(prompt, image=image_b64)
    # For prototype, return dummy data
    return {
        "surname": "DOE",
        "name": "JOHN",
        "occupation": "ENGINEER",
        "gross_monthly_income": 5000.0
    }

@app.route('/upload', methods=['POST'])
def upload_document():
    if 'document' not in request.files or 'document_id' not in request.form:
        return jsonify({"error": "Missing document or document_id"}), 400
    file = request.files['document']
    document_id = request.form['document_id']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.pdf', '.jpg', '.jpeg']:
        return jsonify({"error": "Unsupported file type"}), 400
    image_bytes = file.read()
    # Phase 2: Extraction
    extracted = extract_fields_with_gemini(image_bytes)
    # Phase 3: Validation
    try:
        validated = ExtractedFields(**extracted)
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.errors()}), 422
    # Phase 4: Structured Storage
    doc = DocumentExtraction(
        document_id=document_id,
        surname=validated.surname,
        name=validated.name,
        occupation=validated.occupation,
        gross_monthly_income=validated.gross_monthly_income
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({"document_id": document_id, "fields": validated.dict(), "db_id": doc.id})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
