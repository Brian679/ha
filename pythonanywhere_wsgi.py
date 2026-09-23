"""
PythonAnywhere WSGI configuration for Higher Achievers School Portal.

To use this configuration:
1. Go to the "Web" tab on PythonAnywhere
2. Click "WSGI configuration file" 
3. Replace the content with this file's content
4. Update the paths to match your actual username and project location
"""

import os
import sys

# Add your project directory to the sys.path
path = '/home/YOUR_USERNAME/higherAchievers'
if path not in sys.path:
    sys.path.insert(0, path)

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ['DJANGO_SETTINGS_MODULE'] = 'school_portal.settings'

# Set DEBUG to False for production
os.environ['DEBUG'] = 'False'

# Set your PythonAnywhere domain
os.environ['ALLOWED_HOSTS'] = 'YOUR_USERNAME.pythonanywhere.com,.pythonanywhere.com'

# Optional: Set SECRET_KEY (recommended for production)
# os.environ['SECRET_KEY'] = 'your-secret-key-here'

# Optional: Database URL if using PostgreSQL on PythonAnywhere
# os.environ['DATABASE_URL'] = 'postgresql://YOUR_USERNAME:YOUR_PASSWORD@YOUR_USERNAME.mysql.pythonanywhere.com/YOUR_USERNAME$default'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
