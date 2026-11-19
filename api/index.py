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


class VercelPathCorrectionMiddleware:
    """
    Restores the original browser request path on Vercel.
    Vercel rewrites incoming requests to /api/index and injects the original
    requested URI in HTTP_X_MATCHED_PATH. This middleware restores PATH_INFO
    so Flask routes match correctly.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched_path = environ.get("HTTP_X_MATCHED_PATH")
        if matched_path:
            clean_path = matched_path.split("?")[0]
            if clean_path and clean_path != "/api/index":
                environ["PATH_INFO"] = clean_path
            elif clean_path == "/api/index":
                environ["PATH_INFO"] = "/"
        elif environ.get("PATH_INFO") == "/api/index":
            environ["PATH_INFO"] = "/"
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathCorrectionMiddleware(app.wsgi_app)

