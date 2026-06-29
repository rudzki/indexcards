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
