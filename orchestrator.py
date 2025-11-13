# --- ORCHESTRATOR (Amorce P-5) ---
# v1.1 (Security): Added @require_api_key decorator.
# v1.2 (P-3): Added simulated /v1/a2a/transact endpoint.
# v1.3 (P-4): Updated get_public_key to support Annexe A (UUIDs + status check).
# v1.4 (P-5): Implemented A2A routing logic in /v1/a2a/transact (Tasks 2, 4).

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

# --- Cryptography Imports for Verification ---
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from flask import Flask, request, jsonify, g

# --- Global Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

# --- CRITICAL: Load Security Variables ---

# P-1: Load the Trust Directory URL (for key lookup)
# This was validated and fixed in our P-4 debug.
TRUST_DIRECTORY_URL = os.environ.get("TRUST_DIRECTORY_URL")
if not TRUST_DIRECTORY_URL:
    logging.warning("TRUST_DIRECTORY_URL not set. Signature verification will fail.")

# P-0: Load the API Key (for endpoint security)
AGENT_API_KEY = os.environ.get("AGENT_API_KEY")
if not AGENT_API_KEY:
    logging.warning("AGENT_API_KEY environment variable not set. API will be insecure.")


# --- Authentication Decorator (Security Layer 1) ---
def require_api_key(f: Callable) -> Callable:
    """
    Decorator to ensure the 'X-API-Key' header is present and valid.
    This is the first line of defense.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AGENT_API_KEY:
            logging.warning("Bypassing API key check (server key not set).")
            return f(*args, **kwargs)

        key = request.headers.get('X-API-Key')
        if not key or key != AGENT_API_KEY:
            logging.warning(f"Unauthorized access attempt. Invalid X-API-Key provided.")
            return jsonify({"error": "Unauthorized"}), 401

        g.auth_source = f"Orchestrator (Key: {key[:5]}...)"
        logging.info(f"AUTH_SUCCESS: Valid key received from {g.auth_source}")
        return f(*args, **kwargs)

    return decorated_function


# --- P-1 / P-4 / P-5: Caching & Directory Logic ---

# P-1: Cache for Public Keys (used by L2 validation)
# { "agent_id_uuid": (Ed25519PublicKey, timestamp), ... }
PUBLIC_KEY_CACHE: Dict[str, tuple] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

# P-5.2: NEW Cache for full Agent Records (used by routing)
# { "agent_id_uuid": (dict_record, timestamp), ... }
AGENT_RECORD_CACHE: Dict[str, tuple] = {}


def get_agent_record(agent_id: str) -> Optional[dict]:
    """
    (P-5.2) Fetches the full AgentIdentityRecord from the Trust Directory.
    Implements P-4: Checks the 'status' field.
    Caches the full record for 5 minutes.
    """
    if not TRUST_DIRECTORY_URL:
        logging.error("FATAL: TRUST_DIRECTORY_URL is not set. Cannot verify signatures.")
        return None

    # 1. Check cache first
    cached_data = AGENT_RECORD_CACHE.get(agent_id)
    if cached_data:
        record, timestamp = cached_data
        if (time.time() - timestamp) < CACHE_TTL_SECONDS:
            logging.info(f"Cache HIT (Record) for agent '{agent_id}'.")
            return record
        else:
            logging.info(f"Cache STALE (Record) for agent '{agent_id}'. Fetching...")

    # 2. If not in cache or stale, fetch from Trust Directory
    document_id = agent_id
    lookup_url = f"{TRUST_DIRECTORY_URL}/api/v1/lookup/{document_id}"

    try:
        logging.info(f"Cache MISS (Record). Fetching agent record for '{agent_id}' from: {lookup_url}")
        response = requests.get(lookup_url, timeout=3)

        if response.status_code == 404:
            logging.error(f"Agent lookup failed: Agent ID '{agent_id}' not found in Trust Directory (404).")
            return None

        if response.status_code != 200:
            logging.error(f"Trust Directory returned status {response.status_code}: {response.text}")
            return None

        data = response.json()

        # --- P-4: Status Check ---
        agent_status = data.get("status")
        if agent_status != "active":
            logging.warning(f"Agent lookup failed: Agent '{agent_id}' is not active (status: {agent_status}).")
            return None
        # --- End P-4 Check ---

        # 4. Store in cache and return
        AGENT_RECORD_CACHE[agent_id] = (data, time.time())
        logging.info(f"Successfully fetched and cached record for: {agent_id}")
        return data

    except requests.exceptions.RequestException as e:
        # This is the "Read timed out" error we fixed
        logging.error(f"Agent lookup failed: Could not connect to Trust Directory at {lookup_url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Agent lookup failed: Error parsing record for {agent_id}: {e}")
        return None


def get_public_key(agent_id: str) -> Optional[ed25519.Ed25519PublicKey]:
    """
    (P-4 Updated) Fetches the public key for a given agent_id (UUID).
    (P-5 Refactor): Now uses get_agent_record() to populate its own cache.
    """
    # 1. Check public key cache first
    cached_key_data = PUBLIC_KEY_CACHE.get(agent_id)
    if cached_key_data:
        key, timestamp = cached_key_data
        if (time.time() - timestamp) < CACHE_TTL_SECONDS:
            logging.info(f"Cache HIT (Key) for agent '{agent_id}'.")
            return key
        else:
            logging.info(f"Cache STALE (Key) for agent '{agent_id}'. Fetching...")

    # 2. If key not in cache, get the full record
    # This will use/populate the AGENT_RECORD_CACHE
    record = get_agent_record(agent_id)
    if not record:
        logging.error(f"Signature verification failed: Could not get record for agent '{agent_id}'.")
        return None

    # 3. Extract, load, and cache the public key
    public_key_pem = record.get("public_key")
    if not public_key_pem:
        logging.error(f"Signature verification failed: Record for '{agent_id}' is missing 'public_key'.")
        return None

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))

        # 4. Store in key cache and return
        PUBLIC_KEY_CACHE[agent_id] = (public_key, time.time())
        logging.info(f"Successfully loaded and cached public key for: {agent_id}")
        return public_key
    except Exception as e:
        logging.error(f"Signature verification failed: Error parsing public key for {agent_id}: {e}")
        return None


# --- API Endpoints ---

@app.route("/v1/agent/invoke", methods=["POST"])
@require_api_key  # L1 Security
def invoke_agent():
    """
    (P-1) Legacy endpoint for simple agent tests.
    (P-4): Validated end-to-end.
    """
    try:
        body = request.json
        signature_b64 = request.headers.get('X-Agent-Signature')
        agent_id = body.get("agent_id")  # P-4: This is a UUID
    except Exception as e:
        logging.error(f"Malformed request: {e}")
        return jsonify({"error": "Malformed request."}), 400

    if not all([body, signature_b64, agent_id]):
        return jsonify({"error": "Malformed request."}), 400

    # 2. Get Public Key (L2 Validation)
    public_key = get_public_key(agent_id)
    if not public_key:
        logging.error(f"Zero-Trust Violation: Could not retrieve or validate public key for agent '{agent_id}'.")
        return jsonify({"error": f"Failed to verify agent identity: {agent_id}"}), 403

    # 3. Verify Signature
    try:
        canonical_message = json.dumps(body, sort_keys=True).encode('utf-8')
        signature_bytes = base64.b64decode(signature_b64)
        public_key.verify(signature_bytes, canonical_message)
        logging.info(f"SUCCESS: Signature for agent '{agent_id}' VERIFIED.")
    except InvalidSignature:
        logging.critical(f"FATAL: ZERO-TRUST VIOLATION! Invalid signature for agent '{agent_id}'.")
        return jsonify({"error": "Invalid signature."}), 401
    except Exception as e:
        logging.error(f"Error during signature verification: {e}", exc_info=True)
        return jsonify({"error": "A critical error occurred during signature verification."}), 500

    # 4. Return Success
    return jsonify({
        "status": "Signature verified, task processed (simulation).",
        "received_action": body.get("action")
    }), 200


# --- P-3 / P-5: New Endpoint for A2A Negotiation (ROUTING) ---

@app.route("/v1/a2a/transact", methods=["POST"])
@require_api_key  # L1 Security (API Key)
def a2a_transact():
    """
    (P-5) Handles A2A (Agent-to-Agent) transactions.
    This is the core routing logic of the ATP.
    """

    # --- 1. VALIDATE CONSUMER (Agent A) ---
    try:
        body = request.json  # This is the TransactionRequest
        signature_b64 = request.headers.get('X-Agent-Signature')
        consumer_agent_id = body.get("consumer_agent_id")
    except Exception as e:
        logging.error(f"Malformed A2A request: {e}")
        return jsonify({"error": "Malformed request."}), 400

    if not all([body, signature_b64, consumer_agent_id]):
        return jsonify({"error": "Malformed A2A request (missing body, signature, or consumer_agent_id)."}), 400

    # L2 Validation of Agent A
    public_key_consumer = get_public_key(consumer_agent_id)
    if not public_key_consumer:
        logging.warning(f"A2A Violation: Could not validate Consumer Agent '{consumer_agent_id}'.")
        return jsonify({"error": f"Failed to verify agent identity: {consumer_agent_id}"}), 403

    try:
        canonical_message = json.dumps(body, sort_keys=True).encode('utf-8')
        signature_bytes = base64.b64decode(signature_b64)
        public_key_consumer.verify(signature_bytes, canonical_message)
        logging.info(f"SUCCESS (A2A): Signature for Consumer Agent '{consumer_agent_id}' VERIFIED.")
    except InvalidSignature:
        logging.critical(f"FATAL: A2A VIOLATION! Invalid signature for Consumer Agent '{consumer_agent_id}'.")
        return jsonify({"error": "Invalid signature."}), 401
    except Exception as e:
        logging.error(f"Error during A2A signature verification: {e}", exc_info=True)
        return jsonify({"error": "A critical error occurred during signature verification."}), 500

    # --- 2. LOOKUP SERVICE (P-5.1) ---
    service_id = body.get("service_id")
    if not service_id:
        return jsonify({"error": "TransactionRequest missing 'service_id'."}), 400

    service_lookup_url = f"{TRUST_DIRECTORY_URL}/api/v1/services/{service_id}"
    logging.info(f"A2A Routing: Looking up service '{service_id}' at {service_lookup_url}...")

    try:
        service_response = requests.get(service_lookup_url, timeout=3)
        if service_response.status_code != 200:
            logging.error(f"A2A Routing Error: Service '{service_id}' not found (404) or Directory error.")
            return jsonify({"error": f"Service not found or invalid: {service_id}"}), 404

        service_contract = service_response.json()
        logging.info(f"A2A Routing: Found service '{service_contract.get('service_type')}'")

    except requests.exceptions.RequestException as e:
        logging.error(f"A2A Routing Error: Could not connect to Trust Directory (Service Lookup): {e}")
        return jsonify({"error": "Internal error: Failed to contact Trust Directory"}), 500

    # --- 3. IDENTIFY PROVIDER (P-5.2) ---
    provider_agent_id = service_contract.get("provider_agent_id")
    if not provider_agent_id:
        logging.error(f"A2A Routing Error: Service '{service_id}' has no 'provider_agent_id'.")
        return jsonify({"error": f"Service is misconfigured (missing provider)"}), 500

    logging.info(f"A2A Routing: Identifying provider '{provider_agent_id}'...")
    provider_record = get_agent_record(provider_agent_id)  # Uses our P-4 cache

    if not provider_record:
        logging.error(f"A2A Routing Error: Could not get record for Provider Agent '{provider_agent_id}'.")
        return jsonify({"error": f"Provider agent not found or inactive: {provider_agent_id}"}), 404

    provider_endpoint = provider_record.get("metadata", {}).get("api_endpoint")
    if not provider_endpoint:
        logging.error(f"A2A Routing Error: Provider Agent '{provider_agent_id}' has no 'api_endpoint' in metadata.")
        return jsonify({"error": f"Provider agent is misconfigured (missing endpoint)"}), 500

    # --- 4. PROXY TRANSACTION (P-5.3) ---
    logging.info(f"A2A Routing: Forwarding transaction to provider at: {provider_endpoint}")

    # Forward the L1 API key for the next hop (P-5.3.1)
    proxy_headers = {
        "X-API-Key": AGENT_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        # Forward the *original* TransactionRequest body
        provider_response = requests.post(provider_endpoint, json=body, headers=proxy_headers, timeout=10)

        # --- 5. RELAY RESPONSE (P-5.4) ---
        logging.info(f"A2A Routing: Relaying response (Status {provider_response.status_code}) from provider.")
        # Return the provider's JSON response and status code directly to the consumer
        return provider_response.json(), provider_response.status_code

    except requests.exceptions.RequestException as e:
        logging.error(
            f"A2A Routing Error: Failed to connect to Provider Agent '{provider_agent_id}' at {provider_endpoint}: {e}")
        return jsonify({"error": "Provider agent is offline or unreachable."}), 503  # Service Unavailable


# --- TÂCHE P-5.4: ENDPOINT "ESCLAVE" (SIMULATION AGENT B) ---

@app.route("/v1/services/execute_data_analysis", methods=["POST"])
@require_api_key  # The provider service is *also* secured by our L1 key
def execute_data_analysis():
    """
    (P-5.4) This is a simulated 'provider' (Agent B) endpoint.
    The Orchestrator's routing logic will call this endpoint.
    It receives a TransactionRequest and returns a TransactionResponse.
    """
    try:
        # Get the transaction forwarded by the router
        transaction_request = request.json
        tx_id = transaction_request.get("transaction_id", "unknown-tx")
        payload = transaction_request.get("payload", {})
        logging.info(f"[PROVIDER SIM] Received transaction '{tx_id}' with query: {payload.get('query')}")

    except Exception as e:
        logging.error(f"[PROVIDER SIM] Malformed request: {e}")
        return jsonify({"error": "Malformed request."}), 400

    # Simulate work...

    # Build a TransactionResponse (per White Paper Sec 3.2)
    response_body = {
        "transaction_id": tx_id,
        "status": "success",
        "timestamp": datetime.now(UTC).isoformat(),
        "result": {
            # This matches the 'output_schema' we created in Firestore
            "result": f"The capital of France is Paris. (Simulated by P-5 provider)"
        },
        "error_message": None
    }

    logging.info(f"[PROVIDER SIM] Sending simulated success response for '{tx_id}'")
    return jsonify(response_body), 200


# --- Application Startup ---
if __name__ == '__main__':
    logging.info("Flask Orchestrator (P-5 A2A Routing Ready) initialized successfully.")
    app.run(debug=True, port=int(os.environ.get('PORT', 8080)), host='0.0.0.0')