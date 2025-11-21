# --- ORCHESTRATOR (Nexus NATP v1.0) ---
# Sprint 1: Integrity & Bridge
# Features:
# - L1 Security: API Key (X-API-Key)
# - L2 Security: Ed25519 Signature Verification
# - Bridge: No-Code Gateway via Smart Agent

import os
import json
import logging
import requests
import base64
import time
from datetime import datetime, UTC
from uuid import uuid4
from functools import wraps
from typing import Callable, Any, Optional, Dict

# --- Cryptography Imports ---
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from flask import Flask, request, jsonify, g

# --- IMPORT DU SMART AGENT (Pour le Bridge) ---
import smart_agent as agent

# --- Global Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

# --- CRITICAL: Load Security Variables ---
TRUST_DIRECTORY_URL = os.environ.get("TRUST_DIRECTORY_URL")
AGENT_API_KEY = os.environ.get("AGENT_API_KEY")

if not TRUST_DIRECTORY_URL:
    logging.warning("TRUST_DIRECTORY_URL not set. Signature verification will fail.")
if not AGENT_API_KEY:
    logging.warning("AGENT_API_KEY environment variable not set. API will be insecure.")

# --- Authentication Decorator (Security Layer 1) ---
def require_api_key(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AGENT_API_KEY:
            logging.warning("Bypassing API key check (server key not set).")
            return f(*args, **kwargs)

        # FIX: On garde 'X-API-Key' pour être compatible avec smart_agent.py
        key = request.headers.get('X-API-Key')
        if not key or key != AGENT_API_KEY:
            logging.warning(f"Unauthorized access attempt.")
            return jsonify({"error": "Unauthorized"}), 401

        g.auth_source = f"Orchestrator"
        return f(*args, **kwargs)
    return decorated_function

# --- P-4: Public Key Cache ---
PUBLIC_KEY_CACHE: Dict[str, tuple] = {}
CACHE_TTL_SECONDS = 300

def get_agent_record(agent_id: str) -> Optional[dict]:
    """Fetches Agent Record from Trust Directory."""
    if not TRUST_DIRECTORY_URL:
        return None

    lookup_url = f"{TRUST_DIRECTORY_URL}/api/v1/lookup/{agent_id}"
    try:
        response = requests.get(lookup_url, timeout=3)
        if response.status_code != 200:
            return None
        data = response.json()
        if data.get("status") != "active":
            return None
        return data
    except Exception as e:
        logging.error(f"Agent lookup failed: {e}")
        return None

def get_public_key(agent_id: str) -> Optional[ed25519.Ed25519PublicKey]:
    """Fetches and caches the public key."""
    cached = PUBLIC_KEY_CACHE.get(agent_id)
    if cached and (time.time() - cached[1]) < CACHE_TTL_SECONDS:
        return cached[0]

    record = get_agent_record(agent_id)
    if not record:
        return None

    try:
        pem = record.get("public_key")
        key = serialization.load_pem_public_key(pem.encode('utf-8'))
        PUBLIC_KEY_CACHE[agent_id] = (key, time.time())
        return key
    except Exception:
        return None

# --- API Endpoints ---
def validate_hitl_compliance(body: dict):
    """
    (FR-P1) Enforces Human-In-The-Loop protocol for sensitive transactions.
    Rules:
    1. If intent is 'transaction.commit', a 'human_approval_token' MUST be present.
    """
    # On récupère le payload interne
    payload = body.get("payload", {})

    # On cherche l'intent (soit dans le payload, soit c'est implicite par le contexte)
    # Note: Dans la V1, on surveille spécifiquement les intents critiques
    intent = payload.get("intent")

    # Si c'est un engagement financier (COMMIT), on exige l'humain
    if intent == "transaction.commit":
        token = payload.get("human_approval_token")
        if not token:
            logging.warning(f"HITL Violation: Agent attempted COMMIT without human token.")
            raise ValueError("HITL Violation: 'transaction.commit' requires 'human_approval_token'.")

        logging.info(f"HITL Compliance: Approval token present for transaction.")


@app.route("/v1/a2a/transact", methods=["POST"])
@require_api_key
def a2a_transact():
    """
    Core A2A Routing Endpoint.
    """
    try:
        body = request.json
        signature_b64 = request.headers.get('X-Agent-Signature')
        consumer_id = body.get("consumer_agent_id")

        if not all([body, signature_b64, consumer_id]):
            return jsonify({"error": "Malformed request"}), 400

        # L2 Verification
        pub_key = get_public_key(consumer_id)
        if not pub_key:
            return jsonify({"error": "Identity verification failed"}), 403

        try:
            canonical = json.dumps(body, sort_keys=True).encode('utf-8')
            sig_bytes = base64.b64decode(signature_b64)
            pub_key.verify(sig_bytes, canonical)
        except InvalidSignature:
            return jsonify({"error": "Invalid Signature"}), 401
        try:
            canonical = json.dumps(body, sort_keys=True).encode('utf-8')
            sig_bytes = base64.b64decode(signature_b64)
            pub_key.verify(sig_bytes, canonical)
        except InvalidSignature:
            return jsonify({"error": "Invalid Signature"}), 401

            # --- BEGIN BLOC HITL (new) ---
            # HITL Enforcement (FR-P1)
        try:
            validate_hitl_compliance(body)
        except ValueError as e:
            return jsonify({"error": str(e)}), 403
            # --- END BLOC HITL ---

            # Routing Logic (P-6)
        service_id = body.get("service_id")
        # Routing Logic (P-6)
        service_id = body.get("service_id")
        service_url = f"{TRUST_DIRECTORY_URL}/api/v1/services/{service_id}"

        srv_resp = requests.get(service_url, timeout=3)
        if srv_resp.status_code != 200:
            return jsonify({"error": "Service not found"}), 404

        contract = srv_resp.json()
        provider_id = contract.get("provider_agent_id")

        # Get Provider Endpoint
        prov_record = get_agent_record(provider_id)
        if not prov_record:
             return jsonify({"error": "Provider not found"}), 404

        endpoint = prov_record["metadata"]["api_endpoint"]
        template = contract["metadata"]["service_path_template"]

        # External Call
        payload = body.get("payload", {})
        final_url = f"{endpoint}{template.format(**payload)}"

        ext_resp = requests.get(final_url, timeout=10)
        return jsonify({
            "transaction_id": body.get("transaction_id"),
            "status": "success",
            "result": ext_resp.json()
        })

    except Exception as e:
        logging.error(f"A2A Error: {e}")
        return jsonify({"error": str(e)}), 500


# --- NEW: NEXUS BRIDGE ENDPOINT (FR-O1) ---
@app.route('/v1/nexus/bridge', methods=['POST'])
@require_api_key
def nexus_bridge():
    """
    The Nexus Bridge Endpoint.
    Allows No-Code tools to transact via Smart Agent.
    """
    try:
        req_data = request.json
        if not req_data:
            return jsonify({"error": "Missing JSON payload"}), 400

        service_id = req_data.get("service_id")
        payload = req_data.get("payload")

        if not service_id or not payload:
             return jsonify({"error": "Missing 'service_id' or 'payload'"}), 400

        logging.info(f"BRIDGE: Delegating to Smart Agent for Service {service_id}")

        # Delegated Execution via Smart Agent
        result = agent.run_bridge_transaction(service_id, payload)

        return jsonify(result), 200

    except Exception as e:
        logging.error(f"Bridge Error: {e}")
        return jsonify({"error": str(e)}), 500
# --- END NEXUS BRIDGE ---

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))