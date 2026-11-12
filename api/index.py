"""
Vercel Serverless Function Entrypoint
Exposes the Flask WSGI application object `app` for Vercel's Python runtime.
"""
import os
import sys

# Ensure project root is importable regardless of serverless working directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import create_app

app = create_app()

