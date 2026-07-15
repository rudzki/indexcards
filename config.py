import os

from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(basedir, 'instance', 'indexcards.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5000')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    UPLOAD_DIR = os.path.join(basedir, 'instance', 'uploads')

    # Optional SMTP config via environment. When SMTP_HOST is set here, these
    # values fully override the SMTP fields in Site Settings (see app/mail.py).
    SMTP_HOST = os.environ.get('SMTP_HOST') or None
    SMTP_PORT = int(os.environ['SMTP_PORT']) if os.environ.get('SMTP_PORT', '').isdigit() else None
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME') or None
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD') or None
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
    SMTP_FROM_ADDRESS = os.environ.get('SMTP_FROM_ADDRESS') or None
