"""
Vercel serverless entry point.
Imports the Flask app and exposes it for the @vercel/python builder.
"""
import sys
import os

# Add project root to Python path so `app`, `product_logic`, etc. are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel expects the WSGI app as `app` (already named that from Flask)
