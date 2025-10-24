import os
import subprocess
import tempfile
import PyPDF2
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import re
from datetime import datetime

# --- Configuration ---
# Use environment variables for system-specific paths to make the code portable.
# Users will need to set TESSERACT_CMD in their environment.
pytesseract.pytesseract.tesseract_cmd = os.environ.get('TESSERACT_CMD', r'C:\Program Files\Tesseract-OCR\tesseract.exe')

# --- IMPORTANT SETUP NOTE ---
# This script relies on two external dependencies that must be installed on the system:
# 1. Tesseract OCR (The executable must be in the system's PATH)
# 2. poppler (Required by pdf2image to convert PDF pages to images)

def extract_text_from_pdf(pdf_path):
    """
    Extract text from PDF. Tries direct text extraction first (for text-based PDFs) 
    and falls back to OCR via pdf2image and Tesseract (for image-based/scanned PDFs).
    """
    text = ""
    
    try:
        # 1. Try to extract text directly using PyPDF2
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                extracted_page_text = page.extract_text()
                if extracted_page_text:
                    text += extracted_page_text + "\n"
        
        # 2. If little text was extracted, assume it's an image-based PDF and use OCR
        if len(text.strip()) < 50:
            print("Low text content detected. Falling back to OCR.")
            # Convert PDF pages to images
            images = convert_from_path(pdf_path, dpi=300)
            print(f"Number of images generated from PDF: {len(images)}")
            ocr_text = ""
            for idx, img in enumerate(images):
                try:
                    # Use pytesseract directly on the image
                    ocr_result = pytesseract.image_to_string(img, lang='eng')
                    print(f"OCR result for page {idx+1}: {repr(ocr_result[:100])}...")
                    ocr_text += ocr_result + "\n"
                except Exception as e:
                    print(f"Error during image processing for OCR: {e}")
            # Use OCR text if direct extraction failed
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text

    except PyPDF2.errors.PdfReadError:
        print("PDF Read Error. File might be corrupted or encrypted. Trying OCR directly.")
        # If PyPDF2 fails completely, proceed to OCR as the main method
        try:
            return extract_text_from_image(pdf_path) # pdf2image can often handle files PyPDF2 cannot
        except Exception as e:
            raise Exception(f"OCR failed for potentially corrupted PDF: {str(e)}")
            
    except Exception as e:
        raise Exception(f"General Error processing PDF: {str(e)}")
    
    return text

def extract_text_from_image(image_path):
    """Extract text from a single image using Tesseract OCR via command line"""
    try:
        # Use pytesseract to process the image and output text
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang='eng')
    except Exception as e:
        raise Exception(f"Error processing image with OCR using pytesseract: {e}")

def safe_parse_date(date_str, formats=['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d %b %Y', '%d %B %Y']):
    """Tries to parse a date string using multiple common formats."""
    if not date_str:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def extract_fields_from_text(text):
    """Extract key fields from OCR text using regex patterns"""
    print("\n--- OCR TEXT START ---\n" + text + "\n--- OCR TEXT END ---\n")
    fields = {
        'id_number': None,
        'name': None,
        'date_of_birth': None,
        'gender': None,
        'nationality': None,
        'issue_date': None,
        'expiry_date': None
    }
    # Normalize text for easier matching
    normalized_text = text.upper().replace('|', 'I').replace('0', 'O').replace('1', 'I')
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. ID Number: Zimbabwe format or fallback (handle spaces, dashes, trailing chars)
    id_pattern = re.compile(r'\b\d{2}\s*[- ]\s*\d{6,8}[A-Z0-9]*\b', re.IGNORECASE)
    id_found = False
    for line in lines:
        match = id_pattern.search(line.replace(' ', ''))
        if match:
            fields['id_number'] = match.group(0).replace(' ', '').replace('-', '-').strip()
            id_found = True
            break
    if not id_found:
        match = id_pattern.search(text.replace(' ', ''))
        if match:
            fields['id_number'] = match.group(0).replace(' ', '').replace('-', '-').strip()
    print(f"[DEBUG] Extracted ID number: {fields['id_number']}")

    # 2. Name extraction (robust, context and fallback)
    surname, firstname = '', ''
    for i, line in enumerate(lines):
        # Surname: look for 'SURNAME' label or line
        if 'SURNAME' in line.upper():
            # Try next line, or after colon
            if i+1 < len(lines) and len(lines[i+1]) > 1:
                possible = re.sub(r'[^A-Za-z\- ]', '', lines[i+1]).strip().title()
                if possible:
                    surname = possible
            m = re.search(r'SURNAME[:\s-]*([A-Z\- ]+)', line.upper())
            if m:
                surname = m.group(1).strip().title()
        # First name: look for 'FIRST NAME' or 'GIVEN NAME'
        if 'FIRST NAME' in line.upper() or 'GIVEN NAME' in line.upper():
            if i+1 < len(lines) and len(lines[i+1]) > 1:
                possible = re.sub(r'[^A-Za-z\- ]', '', lines[i+1]).strip().title()
                if possible:
                    firstname = possible
            m = re.search(r'(FIRST|GIVEN) NAME[:\s-]*([A-Z\- ]+)', line.upper())
            if m:
                firstname = m.group(2).strip().title()
    # Fallback: try to extract from a line with both 'SURNAME' and a name
    if not surname:
        for line in lines:
            m = re.match(r'SURNAME\s+([A-Z\- ]+)', line.upper())
            if m:
                surname = m.group(1).title()
    if not firstname:
        for line in lines:
            m = re.match(r'(FIRST|GIVEN) NAME\s+([A-Z\- ]+)', line.upper())
            if m:
                firstname = m.group(2).title()
    # Fallback: try to split a line with two words after 'NAME'
    if not (surname and firstname):
        for line in lines:
            m = re.match(r'NAME[:\s-]*([A-Z\-]+)\s+([A-Z\-]+)', line.upper())
            if m:
                surname, firstname = m.group(1).title(), m.group(2).title()
    # Combine
    if surname and firstname:
        fields['name'] = f"{surname} {firstname}".strip()
    elif surname:
        fields['name'] = surname
    elif firstname:
        fields['name'] = firstname
    print(f"[DEBUG] Extracted name: {fields['name']}")

    # 3. Date extraction: only assign a date if found in context of the correct label (no global fallback)
    date_pattern = re.compile(r'(\d{1,2})\s*([\/\-\s])\s*(\d{1,2})\s*([\/\-\s])\s*(\d{2,4})')
    dob = None
    issue = None
    expiry = None
    def format_date(m):
        d, mth, y = m.group(1), m.group(3), m.group(5)
        if len(y) == 2:
            y = '20' + y if int(y) < 30 else '19' + y
        return f"{d.zfill(2)}/{mth.zfill(2)}/{y}"

    for i, line in enumerate(lines):
        l = line.upper().replace(' ', '')
        # Date of Birth
        if ('DATEOFBIRTH' in l or 'DOB' in l) and not dob:
            print(f"[DEBUG] DOB label found on line {i}: {line}")
            # Try to extract date after label on same line
            m = re.search(r'(?:DATE\s*OF\s*BIRTH|DOB)[^\d]*(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})', line, re.IGNORECASE)
            if m:
                dob = m.group(1).replace(' ', '/').replace('--', '/').replace('-', '/').replace('//', '/').strip()
                print(f"[DEBUG] DOB found after label on same line: {dob}")
            else:
                # If not found, try next line
                if i+1 < len(lines):
                    for m2 in date_pattern.finditer(lines[i+1]):
                        candidate = format_date(m2)
                        print(f"[DEBUG] DOB candidate found on next line {i+1}: {lines[i+1]} -> {candidate}")
                        dob = candidate
                        break
        # Issue Date
        if ('ISSUEDATE' in l or 'DATEOFISSUE' in l or 'DAREOFISSUE' in l) and not issue:
            print(f"[DEBUG] Issue label found on line {i}: {line}")
            m = re.search(r'(?:ISSUE\s*DATE|DATE\s*OF\s*ISSUE|DARE\s*OF\s*ISSUE)[^\d]*(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})', line, re.IGNORECASE)
            if m:
                issue = m.group(1).replace(' ', '/').replace('--', '/').replace('-', '/').replace('//', '/').strip()
                print(f"[DEBUG] Issue date found after label on same line: {issue}")
            else:
                if i+1 < len(lines):
                    for m2 in date_pattern.finditer(lines[i+1]):
                        candidate = format_date(m2)
                        print(f"[DEBUG] Issue candidate found on next line {i+1}: {lines[i+1]} -> {candidate}")
                        issue = candidate
                        break
        # Expiry Date
        if ('EXPIRYDATE' in l or 'VALIDUNTIL' in l) and not expiry:
            print(f"[DEBUG] Expiry label found on line {i}: {line}")
            m = re.search(r'(?:EXPIRY\s*DATE|VALID\s*UNTIL)[^\d]*(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})', line, re.IGNORECASE)
            if m:
                expiry = m.group(1).replace(' ', '/').replace('--', '/').replace('-', '/').replace('//', '/').strip()
                print(f"[DEBUG] Expiry date found after label on same line: {expiry}")
            else:
                if i+1 < len(lines):
                    for m2 in date_pattern.finditer(lines[i+1]):
                        candidate = format_date(m2)
                        print(f"[DEBUG] Expiry candidate found on next line {i+1}: {lines[i+1]} -> {candidate}")
                        expiry = candidate
                        break
    fields['date_of_birth'] = dob
    fields['issue_date'] = issue
    fields['expiry_date'] = expiry
    print(f"[DEBUG] Extracted date of birth: {fields['date_of_birth']}")
    print(f"[DEBUG] Extracted issue date: {fields['issue_date']}")
    print(f"[DEBUG] Extracted expiry date: {fields['expiry_date']}")

    # 6. Gender: match anywhere, fallback to first found
    gender_match = re.search(r'\b(MALE|FEMALE|M|F)\b', text, re.IGNORECASE)
    if gender_match:
        g = gender_match.group(1).upper()
        if g in ['M', 'MALE']:
            fields['gender'] = 'Male'
        elif g in ['F', 'FEMALE']:
            fields['gender'] = 'Female'
    print(f"[DEBUG] Extracted gender: {fields['gender']}")

    # 7. Nationality extraction (unchanged)
    nationality_pattern = r'(?:NATIONALITY|CITIZENSHIP)[:\s-]*\s*([A-Z]+)\b'
    nationality_match = re.search(nationality_pattern, normalized_text)
    if nationality_match:
        fields['nationality'] = nationality_match.group(1).capitalize()
    else:
        for country in ['Zimbabwe', 'South Africa', 'Nigeria', 'Ghana', 'Kenya']:
            if country.upper() in normalized_text:
                fields['nationality'] = country
                break
    print(f"[DEBUG] Extracted nationality: {fields['nationality']}")

    return fields

def process_document(file_path):
    """Main function to process uploaded document (PDF or Image)"""
    try:
        # Determine file type and extract text
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.pdf':
            text = extract_text_from_pdf(file_path)
        elif file_ext in ('.jpg', '.jpeg', '.png', '.tiff'):
            text = extract_text_from_image(file_path)
        else:
            raise ValueError("Unsupported file type.")
        
        # Extract fields from text
        fields = extract_fields_from_text(text)
        
        # Simple quality check based on text extraction
        quality_check = check_document_quality(text)
        
        return {
            'success': True,
            'text': text,
            'fields': fields,
            'quality': quality_check,
            'message': 'Document processed successfully'
        }
        
    except Exception as e:
        # Catch and return any fatal error
        return {
            'success': False,
            'error': str(e),
            'text': '',
            'fields': {},
            'quality': check_document_quality("") # Return default quality check
        }

def check_document_quality(text):
    """
    Simple quality check based on extracted text length and character ratio.
    NOTE: A robust quality check (blurriness, light, orientation) requires 
    image processing libraries like OpenCV, which is not implemented here.
    """
    quality = {
        'is_blank': False,
        # 'is_blurry' is a weak inference based on text quality
        'is_blurry_inferred': False,
        'status_message': 'OK',
        'brightness': 'good',  # default value
        'contrast': 'good'     # default value
    }
    
    clean_text = text.strip()
    
    # Check if blank (no significant text extracted)
    if not clean_text or len(clean_text) < 50:
        quality['is_blank'] = True
        quality['status_message'] = 'DOCUMENT BLANK/UNREADABLE: Too little text extracted.'
        
    # Check for poor OCR quality (inferred blurriness)
    # If the ratio of alphanumeric characters to total length is very low, it suggests bad OCR results.
    if clean_text and len([c for c in clean_text if c.isalnum()]) / max(1, len(clean_text)) < 0.5:
        quality['is_blurry_inferred'] = True
        if not quality['is_blank']:
             quality['status_message'] = 'QUALITY FLAG: Poor text recognition. Document may be blurry or damaged.'
    
    if quality['is_blank'] and quality['is_blurry_inferred']:
         quality['status_message'] = 'FATAL ERROR: Document failed to provide recognizable content.'
            
    return quality

# Example Usage Block (for testing locally)
if __name__ == '__main__':
    # This block requires a test file (e.g., 'sample_id.pdf' or 'sample_scan.jpg') 
    # and the external dependencies (Tesseract, poppler) to be installed.
    # try:
    #     test_file_path = 'sample_id.pdf' 
    #     if os.path.exists(test_file_path):
    #         print(f"--- Processing {test_file_path} ---")
    #         result = process_document(test_file_path)
    #         print(result)
    #     else:
    #         print("Please create a test file (e.g., 'sample_id.pdf') to run the example.")
    # except Exception as e:
    #     print(f"An unexpected error occurred during execution: {e}")
    pass
