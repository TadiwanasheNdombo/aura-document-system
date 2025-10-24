import os
import json
import cv2
import numpy as np
from utils.document_processor import extract_text_from_pdf, extract_text_from_image

def load_config():
    """Loads the configuration from config.json."""
    with open('config.json', 'r') as f:
        return json.load(f)

def classify_account_type(files, config):
    """
    Classifies account type as 'COMPANY' or 'INDIVIDUAL' based on keywords in the documents.
    """
    classification_keywords = config.get('classification_keywords', {})
    for file_path in files:
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext == '.pdf':
                text = extract_text_from_pdf(file_path)
            else:
                text = extract_text_from_image(file_path)
            
            text = text.lower()
            
            if any(keyword in text for keyword in classification_keywords.get('COMPANY', [])):
                return 'COMPANY'
        except Exception as e:
            print(f"Could not read file {file_path} for classification: {e}")
            continue
    return 'INDIVIDUAL' # Default to individual if no company keywords are found

def check_document_quality(file_path):
    """
    Performs quality checks on a document (blurriness and blank page).
    Returns a dictionary with quality metrics.
    """
    quality_report = {'is_blurry': False, 'is_blank': False}
    try:
        img = cv2.imread(file_path)
        if img is None:
            return quality_report

        # 1. Blank Page Detection
        # If the standard deviation of pixel intensity is very low, it's likely a blank page.
        if np.std(img) < 10:
            quality_report['is_blank'] = True

        # 2. Blurriness Check
        # Use the variance of the Laplacian to detect blur. Low variance suggests a blurry image.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < 100: # This threshold can be tuned
            quality_report['is_blurry'] = True
            
    except Exception as e:
        print(f"Error during quality check for {file_path}: {e}")

    return quality_report

def identify_document_type(file_path, config):
    """Identifies the specific type of a document using OCR and keyword matching."""
    doc_keywords = config.get('document_keywords', {})
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext == '.pdf':
            text = extract_text_from_pdf(file_path)
        else:
            text = extract_text_from_image(file_path)
        
        text = text.lower()

        for doc_type, keywords in doc_keywords.items():
            if any(keyword in text for keyword in keywords):
                return doc_type
    except Exception as e:
        print(f"Could not read file {file_path} for identification: {e}")
    
    return "Unknown Document"


def process_package(package_files):
    """
    Orchestrates the entire document package analysis.
    """
    config = load_config()
    
    # 1. Classify Account Type
    account_type = classify_account_type(package_files, config)
    
    # 2. Perform checks on each document
    document_reports = []
    identified_docs = set()
    
    for file_path in package_files:
        doc_type = identify_document_type(file_path, config)
        quality = check_document_quality(file_path)
        
        report = {
            'original_name': os.path.basename(file_path),
            'identified_type': doc_type,
            'quality_issues': []
        }
        if quality['is_blank']:
            report['quality_issues'].append('Blank Page')
        if quality['is_blurry']:
            report['quality_issues'].append('Blurry')
            
        document_reports.append(report)
        if doc_type != "Unknown Document":
            identified_docs.add(doc_type)
            
    # 3. Check for missing documents
    required_docs = set(config['document_checklists'].get(account_type, []))
    missing_docs = list(required_docs - identified_docs)
    
    # 4. Generate final report
    final_report = {
        'account_type': account_type,
        'documents': document_reports,
        'missing_documents': missing_docs,
        'status': 'FLAGGED_FOR_REVIEW' if missing_docs or any(r['quality_issues'] for r in document_reports) else 'CLEAN_FOR_PROCESSING'
    }
    
    return final_report
