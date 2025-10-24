document.addEventListener('DOMContentLoaded', function() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const resultsSection = document.getElementById('resultsSection');
    const loadingSection = document.getElementById('loadingSection');
    const errorSection = document.getElementById('errorSection');
    const previewContainer = document.getElementById('previewContainer');
    const qualityCheck = document.getElementById('qualityCheck');
    const rawTextContainer = document.getElementById('rawTextContainer');
    const editBtn = document.getElementById('editBtn');
    const saveBtn = document.getElementById('saveBtn');
    
    let isEditing = false;
    let currentFileData = null;
    
    // Drag and drop functionality
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight() {
        uploadArea.classList.add('drag-over');
    }
    
    function unhighlight() {
        uploadArea.classList.remove('drag-over');
    }
    
    uploadArea.addEventListener('drop', handleDrop, false);
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length) {
            fileInput.files = files;
            handleFiles(files);
        }
    }
    
    // Only trigger file input if the user clicks directly on the upload area, not on the label/button
    uploadArea.addEventListener('click', (e) => {
        // If the click target is the label or inside the label, do nothing (let label handle it)
        if (e.target.closest('label')) return;
        fileInput.click();
    });
    
    fileInput.addEventListener('change', function() {
        if (this.files.length) {
            handleFiles(this.files);
            // Reset file input immediately so the same file can be selected again
            this.value = '';
        }
    });
    
    function handleFiles(files) {
        const file = files[0];
        
        // Validate file type
        const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
        if (!validTypes.includes(file.type)) {
            showError('Please upload a PDF, JPG, or PNG file');
            return;
        }
        
        // Validate file size (max 16MB)
        if (file.size > 16 * 1024 * 1024) {
            showError('File size must be less than 16MB');
            return;
        }
        
        // Show loading state
        showLoading();
        
        // Upload file
        uploadFile(file);
    }
    
    function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(async response => {
            let data;
            try {
                data = await response.json();
            } catch (e) {
                throw new Error('Invalid server response');
            }
            // Reset file input so the same file can be uploaded again
            fileInput.value = '';
            if (data.success) {
                currentFileData = data;
                displayResults(data);
            } else {
                showError(data.error || 'Failed to process document');
            }
        })
        .catch(error => {
            // Reset file input on error as well
            fileInput.value = '';
            console.error('Error:', error);
            showError(error.message === 'Invalid server response' ? 'Server error: Invalid response.' : 'Network error. Please try again.');
        });
    }
    
    function displayResults(data) {
        // Hide loading, show results
        hideLoading();
        resultsSection.style.display = 'block';
        
        // Display document preview
        displayPreview(data.filename, data.original_name);
        
        // Display quality assessment
        displayQualityCheck(data.quality);
        
        // Populate form fields
        populateForm(data.fields);
        
        // Display raw text
        displayRawText(data.text);
    }
    
    function displayPreview(filename, originalName) {
        const ext = originalName.split('.').pop().toLowerCase();
        previewContainer.innerHTML = '';
        
        if (['jpg', 'jpeg', 'png'].includes(ext)) {
            const img = document.createElement('img');
            img.src = `/files/${filename}`;
            img.alt = 'Document preview';
            previewContainer.appendChild(img);
        } else if (ext === 'pdf') {
            const iframe = document.createElement('iframe');
            iframe.src = `/files/${filename}`;
            iframe.width = '100%';
            iframe.height = '300px';
            previewContainer.appendChild(iframe);
        } else {
            previewContainer.innerHTML = '<p>Preview not available</p>';
        }
    }
    
    function displayQualityCheck(quality) {
        const indicatorsContainer = qualityCheck.querySelector('.quality-indicators');
        indicatorsContainer.innerHTML = '';
        
        const indicators = [
            {
                id: 'blur',
                label: 'Blurriness',
                value: quality.is_blurry ? 'High' : 'Low',
                status: quality.is_blurry ? 'error' : 'good'
            },
            {
                id: 'blank',
                label: 'Blank Page',
                value: quality.is_blank ? 'Yes' : 'No',
                status: quality.is_blank ? 'error' : 'good'
            },
            {
                id: 'brightness',
                label: 'Brightness',
                value: quality.brightness.charAt(0).toUpperCase() + quality.brightness.slice(1),
                status: quality.brightness === 'good' ? 'good' : 'warning'
            },
            {
                id: 'contrast',
                label: 'Contrast',
                value: quality.contrast.charAt(0).toUpperCase() + quality.contrast.slice(1),
                status: quality.contrast === 'good' ? 'good' : 'warning'
            }
        ];
        
        indicators.forEach(indicator => {
            const indicatorEl = document.createElement('div');
            indicatorEl.className = `quality-indicator ${indicator.status}`;
            indicatorEl.innerHTML = `
                <p>${indicator.label}</p>
                <span>${indicator.value}</span>
            `;
            indicatorsContainer.appendChild(indicatorEl);
        });
        
        qualityCheck.style.display = 'block';
    }
    
    function populateForm(fields) {
    document.getElementById('idNumber').value = fields.id_number || '';
    document.getElementById('fullName').value = fields.name || '';
    document.getElementById('dob').value = fields.date_of_birth || '';
    document.getElementById('gender').value = fields.gender || '';
    document.getElementById('nationality').value = fields.nationality || '';
    document.getElementById('issueDate').value = fields.issue_date || '';
    document.getElementById('expiryDate').value = fields.expiry_date || '';
    }

    // Helper: convert DD/MM/YYYY or D/M/YYYY to YYYY-MM-DD for HTML date input
    function toDateInput(val) {
        if (!val) return '';
        // Accept DD/MM/YYYY, D/M/YYYY, DD-MM-YYYY, D-M-YYYY
        const m = val.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
        if (m) {
            const yyyy = m[3];
            const mm = m[2].padStart(2, '0');
            const dd = m[1].padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
        }
        return '';
    }
    
    function displayRawText(text) {
        rawTextContainer.textContent = text || 'No text could be extracted from the document.';
        rawTextSection.style.display = 'block';
    }
    
    // Edit/Save functionality
    editBtn.addEventListener('click', function() {
        if (isEditing) {
            // Save changes
            const inputs = document.querySelectorAll('#dataForm input');
            inputs.forEach(input => {
                input.setAttribute('readonly', true);
            });
            editBtn.textContent = 'Edit Fields';
            saveBtn.disabled = true;
            isEditing = false;
            
            // Here you would typically send the updated data to the server
            alert('Changes saved successfully!');
        } else {
            // Enable editing
            const inputs = document.querySelectorAll('#dataForm input');
            inputs.forEach(input => {
                input.removeAttribute('readonly');
            });
            editBtn.textContent = 'Save Changes';
            saveBtn.disabled = false;
            isEditing = true;
        }
    });
    
    saveBtn.addEventListener('click', function() {
        // This would typically send the data to the server
        alert('Data submitted successfully!');
    });
    
    function showLoading() {
        loadingSection.style.display = 'block';
        resultsSection.style.display = 'none';
        errorSection.style.display = 'none';
    }
    
    function hideLoading() {
        loadingSection.style.display = 'none';
    }
    
    function showError(message) {
        errorSection.style.display = 'block';
        loadingSection.style.display = 'none';
        resultsSection.style.display = 'none';
        document.getElementById('errorText').textContent = message;
    }
    
    window.hideError = function() {
        errorSection.style.display = 'none';
    }
});  
