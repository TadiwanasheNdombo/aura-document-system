import os
import unittest
import tempfile
import shutil
from app import app, users

class AuraTestCase(unittest.TestCase):

    def setUp(self):
        """Set up a test client and a temporary directory for packages."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()

        # Create a temporary directory for packages
        self.test_dir = tempfile.mkdtemp()
        app.config['PACKAGES_DIR'] = os.path.join(self.test_dir, 'packages_to_process')
        app.config['CLEAN_DIR'] = os.path.join(self.test_dir, 'clean_packages')
        app.config['FLAGGED_DIR'] = os.path.join(self.test_dir, 'flagged_for_review')

        os.makedirs(app.config['PACKAGES_DIR'], exist_ok=True)
        os.makedirs(app.config['CLEAN_DIR'], exist_ok=True)
        os.makedirs(app.config['FLAGGED_DIR'], exist_ok=True)

        # Log in the CPC user
        with self.app as client:
            with client.session_transaction() as sess:
                sess['user_id'] = users['cpc_user'].id
                sess['_fresh'] = True

    def tearDown(self):
        """Remove the temporary directory after the test."""
        shutil.rmtree(self.test_dir)

    def test_dashboard_empty(self):
        """Test that the dashboard is accessible and shows no packages initially."""
        response = self.app.get('/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No packages are ready for processing', response.data)

    def test_package_processing_and_dashboard_display(self):
        """Test that a new package is processed and displayed on the dashboard."""
        # Create a dummy package
        package_name = '123456789'
        package_path = os.path.join(app.config['PACKAGES_DIR'], package_name)
        os.makedirs(package_path)
        with open(os.path.join(package_path, 'document1.pdf'), 'w') as f:
            f.write('dummy content')

        # Process the package
        response = self.app.get('/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check that the package is no longer in the processing directory
        self.assertNotIn(package_name, os.listdir(app.config['PACKAGES_DIR']))

        # Check that the package is in the clean directory
        self.assertIn(package_name, os.listdir(app.config['CLEAN_DIR']))

        # Check that the package is displayed on the dashboard
        self.assertIn(bytes(package_name, 'utf-8'), response.data)

    def test_package_detail_page(self):
        """Test that the package detail page is accessible and displays documents."""
        # Create a dummy package in the clean directory
        package_name = '987654321'
        package_path = os.path.join(app.config['CLEAN_DIR'], package_name)
        kyc_path = os.path.join(package_path, 'kyc')
        mandate_path = os.path.join(package_path, 'mandate')
        os.makedirs(kyc_path)
        os.makedirs(mandate_path)

        kyc_doc_name = 'kyc_document.pdf'
        mandate_doc_name = 'mandate_document.pdf'

        with open(os.path.join(kyc_path, kyc_doc_name), 'w') as f:
            f.write('dummy kyc content')
        with open(os.path.join(mandate_path, mandate_doc_name), 'w') as f:
            f.write('dummy mandate content')

        # Access the package detail page
        response = self.app.get(f'/package/{package_name}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check that the document names are present in the response
        self.assertIn(bytes(kyc_doc_name, 'utf-8'), response.data)
        self.assertIn(bytes(mandate_doc_name, 'utf-8'), response.data)

if __name__ == '__main__':
    unittest.main()
