# Higher Achievers School Portal - PythonAnywhere Deployment Guide

## Prerequisites

1. A PythonAnywhere account (paid account recommended for production)
2. Your project code pushed to a Git repository (GitHub, GitLab, etc.)

## Step 1: Upload Your Code

### Option A: Using Git (Recommended)
```bash
# On PythonAnywhere console
cd ~
git clone https://github.com/yourusername/higherAchievers.git
cd higherAchievers
```

### Option B: Using the PythonAnywhere Files Tab
Upload all files through the web interface.

## Step 2: Set Up Virtual Environment

```bash
# On PythonAnywhere console
cd ~/higherAchievers
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 3: Configure Environment Variables

Create a `.env` file in your project root:
```bash
cd ~/higherAchievers
nano .env
```

Add the following content:
```
DEBUG=False
SECRET_KEY=your-very-secure-secret-key-here
ALLOWED_HOSTS=yourusername.pythonanywhere.com,.pythonanywhere.com
```

**Important:** Generate a secure secret key:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Step 4: Set Up Database

### Option A: Use PythonAnywhere MySQL (Free tier)
```bash
# Create MySQL database on PythonAnywhere dashboard
# Then update your .env file:
# DATABASE_URL=mysql://username:password@username.mysql.pythonanywhere.com/username$default

# Install mysqlclient if needed
pip install mysqlclient
```

### Option B: Use PostgreSQL (Paid accounts)
```bash
# Create PostgreSQL database on PythonAnywhere dashboard
# Update your .env file with the PostgreSQL connection string
```

## Step 5: Run Django Migrations

```bash
cd ~/higherAchievers
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
```

## Step 6: Configure WSGI File

1. Go to the **Web** tab on PythonAnywhere
2. Click **WSGI configuration file**
3. Replace the content with the content from `pythonanywhere_wsgi.py` in this repository
4. Update the path to match your username:
   - Change `/home/YOUR_USERNAME/higherAchievers` to `/home/your_actual_username/higherAchievers`
   - Update ALLOWED_HOSTS to your actual domain

## Step 7: Configure Web App

1. In the **Web** tab:
   - Set **Source code** to: `/home/yourusername/higherAchievers`
   - Set **Working directory** to: `/home/yourusername/higherAchievers`
   - Set **WSGI configuration file** to the file you just created

2. Click **Reload** to apply changes

## Step 8: Configure Static Files

In the **Web** tab on PythonAnywhere:
1. Go to the **Static files** section
2. Add the following mappings:
   - **URL**: `/static/`
   - **Directory**: `/home/yourusername/higherAchievers/staticfiles`
   - **URL**: `/media/`
   - **Directory**: `/home/yourusername/higherAchievers/media`

## Step 9: Configure Log Files (Optional but Recommended)

Create log directories:
```bash
cd ~/higherAchievers
mkdir -p logs
```

## Step 10: Set Up Environment Variables in PythonAnywhere

1. In the **Web** tab, scroll to **Environment**
2. Add the following environment variables:
   - `DJANGO_SETTINGS_MODULE` = `school_portal.settings`
   - `PYTHONPATH` = `/home/yourusername/higherAchievers`
   - `SECRET_KEY` = (your secret key from Step 3)
   - `DEBUG` = `False`
   - `ALLOWED_HOSTS` = `yourusername.pythonanywhere.com,.pythonanywhere.com`

## Step 11: Test Your Application

1. Visit `https://yourusername.pythonanywhere.com`
2. Test the application functionality
3. Check the error logs if there are issues (Web tab → Log files)

## Step 12: Set Up Scheduled Tasks (Optional)

If you need to run periodic tasks (like sending email reminders):
1. Go to the **Tasks** tab
2. Set up a scheduled task to run:
   ```bash
   cd /home/yourusername/higherAchievers && /home/yourusername/higherAchievers/venv/bin/python manage.py clearsessions
   ```

## Important Notes

1. **File Uploads**: Media files are stored in the `media/` directory. Make sure this directory exists and has write permissions:
   ```bash
   mkdir -p media
   chmod 755 media
   ```

2. **Database Backups**: PythonAnywhere automatically backs up MySQL databases. For PostgreSQL, set up your own backup strategy.

3. **Static Files**: Always run `python manage.py collectstatic` after updating static files.

4. **Security**: 
   - Never commit `.env` files to version control
   - Use strong passwords for superuser accounts
   - Enable HTTPS (PythonAnywhere provides free HTTPS certificates)

5. **Performance**: 
   - Use a paid account for production use
   - Consider using Django's cache framework for better performance
   - Enable gzip compression in the Web tab

## Troubleshooting

### Static files not loading?
- Run `python manage.py collectstatic` again
- Check that static file mappings are correct in the Web tab
- Verify that `STATIC_ROOT` is set correctly in settings.py

### Database errors?
- Verify your DATABASE_URL is correct
- Make sure the database exists and the user has proper permissions
- Check that the database driver (psycopg or mysqlclient) is installed

### 500 Internal Server Error?
- Check the error log in the Web tab
- Verify all environment variables are set correctly
- Make sure the virtual environment is activated

## Updating Your Application

To update your application after making changes:

```bash
cd ~/higherAchievers
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** in the Web tab.

## Support

For PythonAnywhere-specific issues, consult:
- [PythonAnywhere Help Pages](https://help.pythonanywhere.com/)
- [Django on PythonAnywhere](https://help.pythonanywhere.com/pages/Django/)
