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
TESSERACT_PATH = os.environ.get('TESSERACT_CMD', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Explicitly set the TESSDATA_PREFIX environment variable for the current process.
# This is a more reliable way to ensure Tesseract finds its language data files,
# especially on Windows with paths containing spaces.
tesseract_dir = os.path.dirname(TESSERACT_PATH)
os.environ['TESSDATA_PREFIX'] = os.path.join(tesseract_dir, 'tessdata')

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


def _normalize_text(text):
    """Flattens whitespace and newlines to create a single, space-separated string."""
    return re.sub(r'\s+', ' ', text).strip()


def _find_value(pattern, text, group=1, clean=True):
    """Helper to find a value using regex, with optional cleaning."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        value = match.group(group).strip()
        if clean:
            # Remove common OCR noise like leading/trailing colons, dots, etc.
            return re.sub(r'^[^\w\d]+|[^\w\d]+$', '', value).strip()
        return value
    return None


def _normalize_date(date_str):
    """Parses various date formats and returns a 'YYYY-MM-DD' string."""
    if not date_str:
        return None
    
    # Clean the date string from OCR noise
    date_str = re.sub(r'[^0-9A-Za-z\s/-]', '', date_str).strip()
    
    # Define formats to try, from most to least specific
    formats_to_try = [
        '%d %b %Y',  # 24 Dec 2023
        '%d %B %Y',  # 24 December 2023
        '%d/%m/%Y',  # 24/12/2023
        '%d-%m-%Y',  # 24-12-2023
        '%d/%m/%y',  # 24/12/23
        '%d-%m-%y',  # 24-12-23
        '%m/%d/%Y',  # 12/24/2023
        '%m-%d-%Y',  # 12-24-2023
        '%d.%m.%Y',  # 24.12.2023
        '%y%m%d',    # 851224 (from MRZ)
    ]
    for fmt in formats_to_try:
        try:
            # Handle two-digit years
            dt_obj = datetime.strptime(date_str, fmt)
            if dt_obj.year > datetime.now().year and fmt.endswith('%y'):
                 dt_obj = dt_obj.replace(year=dt_obj.year - 100)
            return dt_obj.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _parse_mrz(text):
    """Parses the Machine-Readable Zone (MRZ) of an ID card."""
    mrz_data = {
        'dob_mrz': None,
        'gender_mrz': None,
        'expiry_mrz': None,
    }
    # Look for a long line characteristic of an MRZ, often starting with ID numbers
    mrz_match = re.search(r'\b\d{6,}[A-Z\d<]{5,}\b', text)
    if mrz_match:
        line = mrz_match.group(0)
        # DOB (YYMMDD) is often followed by gender
        dob_gender_match = re.search(r'(\d{6})([MF<])', line)
        if dob_gender_match:
            mrz_data['dob_mrz'] = dob_gender_match.group(1)
            gender = dob_gender_match.group(2)
            if gender in 'MF':
                mrz_data['gender_mrz'] = gender
        # Expiry Date (YYMMDD) often follows gender
        expiry_match = re.search(r'[MF<](\d{6})', line)
        if expiry_match:
            mrz_data['expiry_mrz'] = expiry_match.group(1)
    return mrz_data


def _find_date_globally(text, keywords):
    """
    Finds a date pattern that is physically close to one of the given keywords in the text.
    This is a powerful fallback for when labels and values are not neatly aligned.
    """
    # A more flexible date pattern that allows for spaces between digits
    date_pattern = r'(\d[\d\s]*[./-]\s*\d[\d\s]*[./-]\s*\d{2,4}|\d[\d\s]*\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\w\s]*\d{2,4})'
    
    for keyword in keywords:
        # Find all occurrences of the keyword and a date, and check their proximity
        keyword_match = re.search(r'\b' + keyword + r'\b', text, re.IGNORECASE)
        date_match = re.search(date_pattern, text, re.IGNORECASE)
        if keyword_match and date_match and abs(keyword_match.start() - date_match.start()) < 150: # Increased proximity radius
            return date_match.group(1)
    return None


def extract_basic_details(ocr_text):
    """Extracts fields for the Basic Details Form from an Account/Mandate card."""
    text = _normalize_text(ocr_text)
    details = {
        "profession": None,
        "employment_status": None,
        "monthly_salary": None,
        "employer_address": None,
    }

    # 1. Profession
    details["profession"] = _find_value(r"(?:OCCUPATION|JOB\s+TITLE|PROFESSION)\s*:*\s*([\w\s-]+)", text)

    # 2. Employment Status (with special logic)
    employer_name = _find_value(r"EMPLOYER'S\s+NAME\s*:*\s*(\w+)", text)
    if employer_name and 'SELF' in employer_name.upper():
        details["employment_status"] = 'Self-Employed'
    else:
        status = _find_value(r"EMPLOYMENT\s+STATUS\s*:*\s*(\w+)", text)
        if status:
            details["employment_status"] = status
        # Fallback if status is not found but employer name is present
        elif employer_name:
            details["employment_status"] = 'Employed'

    # 3. Monthly Salary
    salary_str = _find_value(r"(?:GROSS\s+MONTHLY|SALARY|INCOME\s+AMOUNT)\s*:*\s*\$?\s*([\d,.]+)", text)
    if salary_str:
        details["monthly_salary"] = re.sub(r'[^\d.]', '', salary_str)

    # 4. Employer Address (non-greedy capture until the next major label)
    details["employer_address"] = _find_value(
        r"(?:EMPLOYER'S\s+ADDRESS|ADDRESS:)\s*(.*?)(?:MONTHLY\s+SALARY|TOTAL\s+INCOME|SIGNATURE)",
        text,
        clean=False
    )

    return details


def extract_personal_details(ocr_text):
    """Extracts fields for the Personal Details Form from a scanned ID card."""
    text = _normalize_text(ocr_text)
    details = {
        "full_name": None,
        "id_number": None,
        "date_of_birth": None,
        "gender": None,
        "nationality": None,
        "issue_date": None,
        "expiry_date": None,
    }

    # First, try to parse the MRZ for high-confidence fallback data
    mrz_data = _parse_mrz(text)

    # 1. Full Name (combine surname and given names)
    # Try to find explicit SURNAME and GIVEN NAMES first
    surname = _find_value(r"SURNAME\s*:*\s*([A-Za-z\s'-]+)", text)
    # Made given_names regex more specific to avoid matching "First NAME" as a label
    given_names = _find_value(r"GIVEN\s+NAMES?\s*:*\s*([A-Za-z\s'-]+)", text)
    
    if surname and given_names:
        details["full_name"] = f"{given_names} {surname}"
    else:
        # Fallback 1: Look for a general 'FULL NAME' or 'NAME' label followed by 2-4 words.
        # This regex is more flexible about capitalization for the first word, but subsequent
        # words are expected to be capitalized (common for names).
        full_name_candidate = _find_value(
            r"(?:FULL\s+NAME|NAME)\s*:*\s*([A-Za-z][a-z'-]*\s+[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){0,2})",
            text,
            clean=False # Keep original case for now, will clean 'a' later
        )
        if full_name_candidate:
            # Clean up common OCR noise like isolated 'a' or 'i' within names
            # Also remove misplaced labels from the extracted string
            interim_name = re.sub(r'\b[aAiI]\b', '', full_name_candidate).strip()
            cleaned_name = re.sub(r'First\s+NAME|SURNAME|GIVEN\s+NAMES', '', interim_name, flags=re.IGNORECASE).strip()
            # Final cleanup of any trailing non-alpha chars
            details["full_name"] = re.sub(r'[^\w\s\'-]+$', '', cleaned_name).strip()
        else:
            # Fallback 2: If no explicit labels or general 'NAME' field,
            # try to find a sequence of 2-3 capitalized words that might be a name block.
            # This is a more aggressive pattern for unstructured name blocks.
            # It allows for an optional single lowercase letter (like 'a') between capitalized words.
            name_block_match = re.search(
                r"([A-Z][a-z'-]+\s+[a-z]?\s*[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?)",
                text
            )
            if name_block_match:
                potential_name = name_block_match.group(1).strip()
                # Heuristic: if it contains "First NAME", it's probably not the name itself
                if "First NAME" not in potential_name: # Avoid re-capturing problematic "First NAME TADIWANAS a"
                    interim_name = re.sub(r'\b[aAiI]\b', '', potential_name).strip()
                    cleaned_name = re.sub(r'First\s+NAME|SURNAME|GIVEN\s+NAMES', '', interim_name, flags=re.IGNORECASE).strip()
                    details["full_name"] = re.sub(r'[^\w\s\'-]+$', '', cleaned_name).strip()
            else:
                # Last resort: if only one of surname/given_names was found from explicit labels
                details["full_name"] = surname or given_names

    # 2. ID Number
    details["id_number"] = _find_value(r"(?:IDN|I\.D\.\s+NO|NATIONAL\s+ID\s+NUMBER)\s*:*\s*([\w\d\s-]+)", text)
    # Fallback: If no ID found via label, look for common ID patterns directly
    if not details["id_number"]:
        # Pattern for formats like ##-#######A## or ##-####### A ##
        id_match = re.search(r'\b(\d{2}[- ]?\d{6,8}[- ]?[A-Z][- ]?\d{2})\b', text)
        if id_match:
            details["id_number"] = id_match.group(1)

    # 3. Date of Birth
    # Look for date on same line or next line after label
    dob_str = (
        _find_value(r"(?:DATE\s+OF\s+BIRTH|DOB|BIRTH\s+DATE)\s*:*\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", text) or 
        _find_value(r"(?:DATE\s+OF\s+BIRTH|DOB|BIRTH\s+DATE)\s*:*\s*\n\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", ocr_text) or
        _find_date_globally(text, ['BIRTH', 'DOB'])
    )
    details["date_of_birth"] = _normalize_date(dob_str or mrz_data.get('dob_mrz'))

    # 4. Gender Extraction
    # Tier 1: Look for a label like "Sex"
    gender_str = _find_value(r'(?:SEX|GENDER)\s*:*\s*([MF])\b', text)
    # Tier 2: Look for standalone gender words or letters
    gender_match = re.search(r'\b(MALE|FEMALE|M|F)\b', text, re.IGNORECASE) if not gender_str else None
    
    final_gender_char = gender_str or (gender_match.group(1) if gender_match else None)
    
    if final_gender_char:
        if final_gender_char.upper().startswith('M'):
            details['gender'] = 'Male'
        elif final_gender_char.upper().startswith('F'):
            details['gender'] = 'Female'
    # Fallback to MRZ gender
    if not details['gender'] and mrz_data.get('gender_mrz'):
        if mrz_data['gender_mrz'] == 'M':
            details['gender'] = 'Male'
        elif mrz_data['gender_mrz'] == 'F':
            details['gender'] = 'Female'

    # 5. Nationality
    # Comprehensive list of nationalities and country names for better matching.
    nationality_map = {
        'ZIMBABWEAN': 'Zimbabwean', 'ZIMBABWE': 'Zimbabwean',
        'SOUTH AFRICAN': 'South African', 'SOUTH AFRICA': 'South African',
        'NIGERIAN': 'Nigerian', 'NIGERIA': 'Nigerian',
        'KENYAN': 'Kenyan', 'KENYA': 'Kenyan',
        'GHANAIAN': 'Ghanaian', 'GHANA': 'Ghanaian',
        'BOTSWANAN': 'Botswanan', 'BOTSWANA': 'Botswanan',
        'ZAMBIAN': 'Zambian', 'ZAMBIA': 'Zambian',
        'MALAWIAN': 'Malawian', 'MALAWI': 'Malawian',
        'MOZAMBICAN': 'Mozambican', 'MOZAMBIQUE': 'Mozambican',
        'AMERICAN': 'American', 'UNITED STATES': 'American',
        'BRITISH': 'British', 'UNITED KINGDOM': 'British',
        'CANADIAN': 'Canadian', 'CANADA': 'Canadian',
        'AUSTRALIAN': 'Australian', 'AUSTRALIA': 'Australian',
        'INDIAN': 'Indian', 'INDIA': 'Indian',
        'CHINESE': 'Chinese', 'CHINA': 'Chinese'
    }
    nationality_keywords = list(nationality_map.keys())
    nationality_pattern = r'\b(' + '|'.join(nationality_keywords) + r')\b'

    # Tier 1: Search for nationality next to a label.
    found_nationality_keyword = _find_value(r"(?:NATIONALITY|NAT\.?|CITIZENSHIP)\s*[:.\s-]*" + nationality_pattern, text, group=2)
    # Tier 2: If not found, search for any nationality keyword globally in the text.
    if not details["nationality"]:
        found_nationality_keyword = _find_value(nationality_pattern, text, group=1)
    
    if found_nationality_keyword:
        details["nationality"] = nationality_map.get(found_nationality_keyword.upper())

    # 6. Issue Date
    issue_date_str = (
        _find_value(r"(?:ISSUE\s+DATE|ISSUED\s+ON|DATE\s+OF\s+ISSUE)\s*:*\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", text) or 
        _find_value(r"(?:ISSUE\s+DATE|ISSUED\s+ON|DATE\s+OF\s+ISSUE)\s*:*\s*\n\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", ocr_text) or
        _find_date_globally(text, ['ISSUE', 'ISSUED'])
    )
    details["issue_date"] = _normalize_date(issue_date_str)

    # 7. Expiry Date
    expiry_date_str = (
        _find_value(r"(?:EXPIRY\s+DATE|EXP\.?|VALID\s+UNTIL)\s*:*\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", text) or 
        _find_value(r"(?:EXPIRY\s+DATE|EXP\.?|VALID\s+UNTIL)\s*:*\s*\n\s*([\d\s./-]+[A-Za-z\s]*\d{2,4})", ocr_text) or
        _find_date_globally(text, ['EXPIRY', 'VALID', 'EXP'])
    )
    details["expiry_date"] = _normalize_date(expiry_date_str or mrz_data.get('expiry_mrz'))

    return details


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
        
        # --- Intelligent Extractor Selection ---
        # Decide which extractor to use based on keywords in the OCR text.
        normalized_text_for_check = text.upper()
        fields = {}

        # Check for keywords that indicate an Account/Mandate Form
        if 'EMPLOYMENT STATUS' in normalized_text_for_check or 'OCCUPATION' in normalized_text_for_check or 'MONTHLY SALARY' in normalized_text_for_check:
            print("[DEBUG] Document identified as Account/Mandate Form. Running basic details extraction.")
            fields = extract_basic_details(text)
        # Default to personal details extraction (for ID cards, etc.)
        else:
            print("[DEBUG] Document identified as ID Card. Running personal details extraction.")
            fields = extract_personal_details(text)
        
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
    import json

    # --- 1. Test Basic Details Extraction (from Account Form) ---
    account_form_ocr = """
    3. EMPLOYMENT STATUS
    Please tick one and provide details below
    
    OCCUPATION:....CHEF & RESTAURANT OWNER
    
    EMPLOYER'S NAME.......... SELF
    
    EMPLOYER'S ADDRESS: 123 CULINARY LANE, GOURMET CITY, ZIM
    
    MONTHLY SALARY INCOME (ATTACH PAYSLIP)
    GROSS MONTHLY $ 2,500.00
    OTHER INCOME $ 500
    TOTAL INCOME $ 3,000.00
    
    4. SIGNATURE
    ...
    """
    print("\n--- Testing Basic Details Extraction ---")
    basic_data = extract_basic_details(account_form_ocr)
    print(json.dumps(basic_data, indent=2))

    # --- 2. Test Personal Details Extraction (from ID Card) ---
    id_card_ocr = """
    REPUBLIC OF ZIMBABWE
    NATIONAL REGISTRATION
    
    IDN: 63-2001234-A-42
    
    SURNAME: CHITEZA
    GIVEN NAMES: CLETOS
    
    DATE OF BIRTH: 24/12/1985
    
    VILLAGE OF ORIGIN: MUTARE
    PLACE OF BIRTH: HARARE
    
    NAT. ZIMBABWEAN
    
    DATE OF ISSUE: 15-06-2017
    
    EXPIRY DATE: 14 JUN 2027
    
    <CLETOS<<CHITEZA<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    632001234A42ZWE8512248M2706143<<<<<<<<<<<<<<04
    """
    print("\n--- Testing Personal Details Extraction ---")
    personal_data = extract_personal_details(id_card_ocr)
    print(json.dumps(personal_data, indent=2))
