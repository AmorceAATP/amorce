"""
Orchestrator (Transport Layer) - Amorce Project (v3.3 - Phase 4)

This file manages the Flask API, which serves as the "Transport Layer" for the agent.
It handles two primary responsibilities:
1.  Authentication (via API Key) using the @require_api_key decorator.
2.  Signature Verification (Phase 4): It intercepts the 'signed_task' from the 
    AgentClient, fetches the agent's public key from the Trust Directory,
    and cryptographically verifies the signature *before* sending the
    response to the end-user.
"""

import os
import json
import logging
import requests  # <-- PHASE 4 IMPORT
import base64    # <-- PHASE 4 IMPORT
from functools import wraps
from pathlib import Path
from typing import Callable, Any, Optional

# --- PHASE 4: Cryptography Imports for Verification ---
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from flask import Flask, request, jsonify

# --- PHASE 3: Import the *real* AgentClient ---
# This ensures we are not using the old simulator.
from agent_client import AgentClient

# --- Global Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

# Load the single API key from the environment
API_KEY = os.environ.get("AGENT_API_KEY")
if not API_KEY:
    logging.warning("AGENT_API_KEY environment variable not set. API will be insecure.")

# --- PHASE 4: Load the Trust Directory URL ---
# The orchestrator needs this to *look up* public keys for verification.
TRUST_DIRECTORY_URL = os.environ.get("TRUST_DIRECTORY_URL")
if not TRUST_DIRECTORY_URL:
    logging.warning("TRUST_DIRECTORY_URL not set. Signature verification will fail.")

# --- Authentication Decorator (Security Layer 1) ---
def require_api_key(f: Callable) -> Callable:
    """
    Decorator to ensure the 'X-ATP-Key' header is present and valid.
    This is the first line of defense.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not API_KEY:
            # If no API_KEY is set on the server, bypass auth (insecure mode)
            logging.warning("Bypassing API key check (server key not set).")
            return f(*args, **kwargs)

        key = request.headers.get('