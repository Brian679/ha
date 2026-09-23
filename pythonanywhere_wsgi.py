"""
PythonAnywhere WSGI configuration for Higher Achievers School Portal.

This configuration works for both local development and PythonAnywhere deployment.
For PythonAnywhere, update the project_home path to match your actual username.
"""

import os
import sys

# Add your project directory to the sys.path
# For PythonAnywhere: use '/home/YourUsername/YourProject'
# For local development: this will be detected automatically
project_home = '/home/HigherAchieversAcademy/HigherAchievers'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['DJANGO_SETTINGS_MODULE'] = 'school_portal.settings'

# Detect if running on PythonAnywhere
is_pythonanywhere = 'pythonanywhere' in project_home.lower() or os.path.exists(os.path.join(project_home, 'pythonanywhere_wsgi.py'))

if is_pythonanywhere:
    # Production settings for PythonAnywhere
    os.environ['DEBUG'] = 'False'
    os.environ['SECRET_KEY'] = 'your-secret-key-here'  # Replace with actual secret key
    os.environ['ALLOWED_HOSTS'] = 'HigherAchieversAcademy.pythonanywhere.com,.pythonanywhere.com'
else:
    # Local development settings
    os.environ.setdefault('DEBUG', 'True')
    os.environ.setdefault('SECRET_KEY', 'django-insecure-development-only-change-me')
    os.environ.setdefault('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')

# Serve Django via WSGI
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
