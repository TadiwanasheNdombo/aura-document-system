import os
import shutil
import json
import mimetypes
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import utils.package_processor as package_processor
import utils.document_processor as document_processor
from flask_sqlalchemy import SQLAlchemy
from db_models import HTRResult

# Engine Declaration
# The engine responsible for text recognition in this Active Learning prototype is the Google GenAI SDK (Gemini).
# It functions as an HTR (Handwritten Text Recognition) and ICR (Intelligent Character Recognition) engine,
# which is necessary for the high-accuracy extraction of both handwritten forms and structured ID documents.
# Standard OCR is specifically not used for this task.

app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.config['SECRET_KEY'] = 'a-very-secret-key-that-should-be-changed' # Change this in production

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:root@localhost:5432/aura_db'  # Update as needed
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- User Management Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

class User(UserMixin):
    def __init__(self, id, username, password, role):
        self.id = id
        self.username = username
        self.password = password
        self.role = role # 'BRANCH' or 'CPC'

# In-memory user store (for demonstration purposes)
users = {
    'branch_user': User('1', 'branch_user', 'password123', 'BRANCH'),
    'cpc_user': User('2', 'cpc_user', 'password123', 'CPC')
}

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGES_DIR = os.path.join(BASE_DIR, 'packages_to_process')
CLEAN_DIR = os.path.join(BASE_DIR, 'clean_packages')
FLAGGED_DIR = os.path.join(BASE_DIR, 'flagged_for_review')

# Ensure all necessary directories exist
os.makedirs(PACKAGES_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(FLAGGED_DIR, exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    """Loads user for session management."""
    for user in users.values():
        if user.id == user_id:
            return user
    return None

@app.route('/', methods=['GET', 'POST'])
def index():
    """Handles user login and redirects authenticated users."""
    if current_user.is_authenticated:
        if current_user.role == 'CPC':
            return redirect(url_for('dashboard'))
        elif current_user.role == 'BRANCH':
            return redirect(url_for('upload_package'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)
        if user and user.password == password:
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def process_packages():
    """
    Scans the PACKAGES_DIR, processes each package, and moves it to the
    appropriate clean or flagged directory.
    """
    if not os.path.exists(PACKAGES_DIR):
        return

    for package_name in os.listdir(PACKAGES_DIR):
        package_path = os.path.join(PACKAGES_DIR, package_name)
        if not os.path.isdir(package_path):
            continue

        # Gather all file paths, excluding package_info.json
        files = [os.path.join(dp, f) for dp, dn, fn in os.walk(package_path) for f in fn if f != 'package_info.json']
        
        if not files:
            # Clean up empty directories
            try:
                shutil.rmtree(package_path)
            except OSError as e:
                print(f"Error removing empty directory {package_path}: {e}")
            continue

        # Process the package
        report = package_processor.process_package(files)
        
        destination_folder = CLEAN_DIR if report['status'] == 'CLEAN_FOR_PROCESSING' else FLAGGED_DIR
        final_package_path = os.path.join(destination_folder, package_name)

        try:
            if os.path.exists(final_package_path):
                shutil.rmtree(final_package_path)
            shutil.move(package_path, final_package_path)

            # Generate and save the report
            report_lines = [
                f"AURA Pre-Check Report for Package: {package_name}",
                "==================================================",
                f"Detected Account Type: {report['account_type']}",
                f"Overall Status: {report['status']}",
                "\n--- DOCUMENT SUMMARY ---"
            ]
            for doc_report in report['documents']:
                original_name = doc_report['original_name']
                identified_type = doc_report['identified_type'].replace(' ', '_')
                _, file_ext = os.path.splitext(original_name)
                new_name = f"{report['account_type']}_{identified_type}{file_ext}"

                # Find the original file's subdirectory (e.g., 'kyc', 'mandate') to preserve it
                original_file_full_path = doc_report.get('file_path') # Assuming package_processor returns this
                relative_dir = os.path.dirname(os.path.relpath(original_file_full_path, package_path)) if original_file_full_path else ''
                target_dir = os.path.join(final_package_path, relative_dir)
                
                # Ensure the target subdirectory (e.g., .../clean_packages/12345/mandate) exists
                os.makedirs(target_dir, exist_ok=True)
                
                # The original file is now inside final_package_path. We need to construct its current path.
                # The file is in its subdirectory relative to the new final_package_path
                current_original_file_path = os.path.join(final_package_path, relative_dir, original_name)
                new_file_path = os.path.join(target_dir, new_name)
                if os.path.exists(current_original_file_path) and not os.path.exists(new_file_path):
                    os.rename(current_original_file_path, new_file_path)
                
                report_lines.append(f"\nFile: {new_name} (Original: {original_name})")
                report_lines.append(f"  - Identified as: {doc_report['identified_type']}")
                if doc_report['quality_issues']:
                    report_lines.append(f"  - Quality Flags: {', '.join(doc_report['quality_issues'])}")

            if report['missing_documents']:
                report_lines.append("\n--- MISSING DOCUMENTS ---")
                report_lines.extend([f"  - {missing}" for missing in report['missing_documents']])

            with open(os.path.join(final_package_path, '_Pre-Check_Report.txt'), 'w') as f:
                f.write("\n".join(report_lines))

        except Exception as e:
            print(f"Error processing package {package_name}: {e}")


@app.route('/dashboard')
@login_required
def dashboard():
    """
    Displays a report of all processed packages on the dashboard.
    """
    if current_user.role != 'CPC':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('index'))

    # Process any new packages first
    process_packages()

    processed_packages = []
    all_dirs = {CLEAN_DIR: "CLEAN_FOR_PROCESSING", FLAGGED_DIR: "FLAGGED_FOR_REVIEW"}

    for dir_path, status in all_dirs.items():
        if not os.path.exists(dir_path):
            continue
        for package_name in os.listdir(dir_path):
            package_dir_path = os.path.join(dir_path, package_name)
            if not os.path.isdir(package_dir_path):
                continue

            package_info_path = os.path.join(package_dir_path, 'package_info.json')
            account_name, branch_name, account_type = "Unknown", "Unknown", "Unknown"

            if os.path.exists(package_info_path):
                with open(package_info_path, 'r') as f:
                    package_info = json.load(f)
                    account_name = package_info.get('account_name', 'Unknown')
                    branch_name = package_info.get('branch_name', 'Unknown')
                    account_type = package_info.get('account_type', 'Unknown')

            processed_packages.append({
                'name': package_name,
                'status': status,
                'account_name': account_name,
                'branch': branch_name,
                'account_type': account_type
            })
            
    return render_template('dashboard.html', packages=processed_packages)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_package():
    """Page for BRANCH users to upload document packages."""
    if current_user.role != 'BRANCH':
        flash('Access denied. You do not have permission to view this page.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        account_no = request.form.get('account_no')
        account_name = request.form.get('account_name')
        branch_name = request.form.get('branch_name')
        account_type = request.form.get('account_type')
        kyc_docs = request.files.getlist('kyc_docs')
        mandate_docs = request.files.getlist('mandate_docs')

        all_files = kyc_docs + mandate_docs
        if not account_no or not all_files or all(f.filename == '' for f in all_files):
            flash('Account number and at least one file (KYC or Mandate) are required.', 'danger')
            return redirect(request.url)

        # Use account_no as the package name
        package_name = account_no
        safe_package_name = secure_filename(package_name)
        package_upload_path = os.path.join(PACKAGES_DIR, safe_package_name)
        
        # Create subdirectories
        kyc_path = os.path.join(package_upload_path, 'kyc')
        mandate_path = os.path.join(package_upload_path, 'mandate')
        os.makedirs(kyc_path, exist_ok=True)
        os.makedirs(mandate_path, exist_ok=True)

        # Save package info
        package_info = {
            'account_no': account_no,
            'account_name': account_name,
            'branch_name': branch_name,
            'account_type': account_type
        }
        with open(os.path.join(package_upload_path, 'package_info.json'), 'w') as f:
            json.dump(package_info, f, indent=4)

        # Save files to their respective directories
        for file in kyc_docs:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(kyc_path, filename))
        
        for file in mandate_docs:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(mandate_path, filename))
        
        # Process the newly uploaded package immediately
        process_packages()

        flash(f'Package for account "{package_name}" uploaded successfully and is queued for processing.', 'success')
        return redirect(url_for('upload_package'))

    return render_template('upload.html')

@app.route('/package/<package_name>')
@login_required
def package_detail(package_name):
    """Displays the two-column processing view for a single package."""
    if current_user.role != 'CPC':
        return redirect(url_for('index'))

    # Find the package in either clean or flagged directories
    package_path = None
    if os.path.exists(os.path.join(CLEAN_DIR, package_name)):
        package_path = os.path.join(CLEAN_DIR, package_name)
    elif os.path.exists(os.path.join(FLAGGED_DIR, package_name)):
        package_path = os.path.join(FLAGGED_DIR, package_name)

    if not package_path:
        flash('Package not found.', 'danger')
        return redirect(url_for('dashboard'))

    # Recursively find all documents within the package directory
    kyc_docs = []
    mandate_docs = []
    
    print(f"--- Starting categorization for package: {package_name} ---")
    for root, _, files in os.walk(package_path):
        for filename in files:
            if filename.lower() in ['_pre-check_report.txt', 'package_info.json']:
                continue

            # Create a relative path from the package_path to the file
            relative_path = os.path.relpath(os.path.join(root, filename), package_path)
            # Get the first directory in the relative path to determine the category
            path_parts = relative_path.split(os.path.sep)
            # If the path has a directory (e.g., 'mandate/file.pdf'), the first part is the category.
            # Otherwise, the file is in the root, and we can't determine a category from the path.
            category_dir = path_parts[0] if len(path_parts) > 1 else None
            
            print(f"Processing file: {relative_path}, Category Dir: {category_dir}") # DEBUG

            # Categorize based on the directory it's in
            if category_dir == 'mandate':
                mandate_docs.append(relative_path.replace('\\', '/'))
                print(f"  -> Categorized as: Mandate") # DEBUG
            else:
                kyc_docs.append(relative_path.replace('\\', '/'))
                print(f"  -> Categorized as: KYC") # DEBUG
    print("--- Categorization complete ---")

    # Load basic details from package_info.json
    package_info = {}
    package_info_path = os.path.join(package_path, 'package_info.json')
    if os.path.exists(package_info_path):
        with open(package_info_path, 'r') as f:
            package_info = json.load(f)

    return render_template('package_detail.html', 
                           package_name=package_name, 
                           kyc_documents=kyc_docs, 
                           mandate_documents=mandate_docs, 
                           package_info=package_info)

@app.route('/view_document/<package_name>/<path:filename>')
@login_required
def view_document(package_name, filename):
    """Serves a document file from its package folder."""
    if current_user.role != 'CPC':
        return "Access Denied", 403

    print(f"DEBUG: view_document called for package: {package_name}, filename: {filename}")

    # Determine the base directory
    package_dir = None
    if os.path.exists(os.path.join(CLEAN_DIR, package_name)):
        package_dir = os.path.join(CLEAN_DIR, package_name)
        print(f"DEBUG: Package found in CLEAN_DIR: {package_dir}")
    elif os.path.exists(os.path.join(FLAGGED_DIR, package_name)):
        package_dir = os.path.join(FLAGGED_DIR, package_name)
        print(f"DEBUG: Package found in FLAGGED_DIR: {package_dir}")

    if package_dir:
        # Securely join the path and normalize it to prevent directory traversal attacks.
        # os.path.normpath is crucial here.
        safe_path = os.path.normpath(os.path.join(package_dir, filename))
        print(f"DEBUG: Constructed safe_path: {safe_path}")

        # Security check: ensure the resolved path is still within the package directory
        if not safe_path.startswith(os.path.normpath(package_dir)):
            print(f"SECURITY ALERT: Path traversal attempt detected for {safe_path} outside {package_dir}")
            return "Forbidden", 403

        if os.path.exists(safe_path):
            # send_from_directory needs the directory and the filename separately.
            directory, file = os.path.split(safe_path)
            # Explicitly set the mimetype to prevent browser download prompts
            mimetype, _ = mimetypes.guess_type(safe_path)
            print(f"DEBUG: Serving file {file} with mimetype: {mimetype}")
            return send_from_directory(directory, file, mimetype=mimetype)
    
    print(f"DEBUG: File not found or package_dir not determined for {package_name}/{filename}")
    return "File not found", 404


@app.route('/old_index')
def old_index():
    """Provides access to the original single-file upload page for reference."""
    return render_template('index.html')

@app.route('/submit_and_delete_package/<package_name>', methods=['POST'])
@login_required
def submit_and_delete_package(package_name):
    """
    Deletes a package directory after it has been processed.
    """
    if current_user.role != 'CPC':
        return jsonify({'success': False, 'error': 'Access Denied'}), 403

    package_to_delete = None
    
    # Check in CLEAN_DIR
    path_in_clean = os.path.join(CLEAN_DIR, package_name)
    if os.path.isdir(path_in_clean):
        package_to_delete = path_in_clean
        
    # Check in FLAGGED_DIR
    path_in_flagged = os.path.join(FLAGGED_DIR, package_name)
    if os.path.isdir(path_in_flagged):
        package_to_delete = path_in_flagged

    if package_to_delete:
        try:
            shutil.rmtree(package_to_delete)
            flash(f'Package "{package_name}" has been processed and removed.', 'success')
            return jsonify({'success': True, 'redirect_url': url_for('dashboard', _anchor='account-opening-section')})
        except Exception as e:
            print(f"Error deleting folder {package_name}: {e}")
            return jsonify({'success': False, 'error': 'Error deleting package.'}), 500
    else:
        return jsonify({'success': False, 'error': 'Package not found.'}), 404

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

import os
import shutil
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import utils.package_processor as package_processor
import utils.document_processor as document_processor
