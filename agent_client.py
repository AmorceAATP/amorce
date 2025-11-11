import requests
import os
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from google.cloud import secretmanager  # New import
import base64
import json

# --- Configuration ---
# *** MISE À JOUR : Pointeur vers l'URL de production ***
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL",
                                  "https://amorce-api-425870997313.us-central1.run.app/v1/agent/invoke")
AGENT_ID = os.environ.get("AGENT_ID", "agent-007")

# *** NOUVEAU : Clé API pour s'authentifier auprès de l'Orchestrateur ***
AGENT_API_KEY = os.environ.get("AGENT_API_KEY")

# GCP Project ID where the secret is stored.
GCP_PROJECT_ID = "amorce-prod-rgosselin"

# Secret name as created in step 1
SECRET_NAME = "atp-agent-private-key"

# In-memory cache for the private key
_private_key_cache = None


def _get_key_from_secret_manager():
    """
    Fetches the private key from GCP Secret Manager.
    This function is called once on startup.
    """
    global _private_key_cache
    if _private_key_cache:
        return _private_key_cache

    try:
        print(f"Loading private key from Secret Manager: {SECRET_NAME}...")
        client = secretmanager.SecretManagerServiceClient()

        # Build the resource name of the secret version
        name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"

        # Access the secret version
        response = client.access_secret_version(request={"name": name})

        # Extract the PEM data (in bytes)
        pem_data = response.payload.data

        # Load the key from the bytes
        _private_key_cache = serialization.load_pem_private_key(
            pem_data,
            password=None,
            backend=default_backend()
        )
        print("Private key loaded into memory successfully.")
        return _private_key_cache

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load private key from Secret Manager.")
        print(f"Error: {e}")
        # The application cannot function without this key.
        # In a real scenario, this should prevent the container from starting.
        raise


def sign_message(message_body):
    """
    Signs a message body (dict) using the in-memory private key.
    """
    private_key = _get_key_from_secret_manager()

    # The message must be canonicalized for the signature to be consistent.
    # Use json.dumps with sort_keys=True for deterministic serialization
    canonical_message = json.dumps(message_body, sort_keys=True).encode('utf-8')

    # --- CORRECTION ---
    # The original code assumed an RSA key with PSS padding.
    # The error "Ed25519PrivateKey.sign()" tells us this is an Ed25519 key.
    # The Ed25519 `sign` method is simpler and takes only the message data.
    signature = private_key.sign(
        canonical_message
    )
    # --- END OF CORRECTION ---

    # Return the signature as Base64 for HTTP transport
    return base64.b64encode(signature).decode('utf-8')


def send_signed_request(action, text):
    """
    Builds, signs, and sends a request to the orchestrator.
    """
    print(f"Sending signed request to {ORCHESTRATOR_URL}...")

    body = {
        "agent_id": AGENT_ID,
        "action": action,
        "text": text,
        "timestamp": int(time.time())
    }

    # Sign the request body
    try:
        signature = sign_message(body)
    except Exception as e:
        print(f"Failed to sign message: {e}")
        return

    headers = {
        "X-Agent-Signature": signature,
        "Content-Type": "application/json"
    }

    # *** NOUVEAU : Ajouter la clé API (Couche de Sécurité 1) ***
    if AGENT_API_KEY:
        headers["X-API-Key"] = AGENT_API_KEY
    else:
        print("CRITICAL: AGENT_API_KEY environment variable not set. Request will fail authentication.")
        return
    # *** FIN DE L'AJOUT ***

    try:
        response = requests.post(ORCHESTRATOR_URL, json=body, headers=headers, timeout=10)

        if response.status_code == 200:
            print("Orchestrator Response (Success):")
            print(response.json())
        elif response.status_code == 401:
            print("Orchestrator Response (Error 401 Unauthorized):")
            print("The signature was rejected by the server.")
            print(response.json())
        else:
            print(f"Orchestrator Response (Error {response.status_code}):")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to orchestrator: {e}")


if __name__ == "__main__":
    # Ensure the key is loaded on startup
    try:
        _get_key_from_secret_manager()

        # Send a test request
        send_signed_request(
            action="query_nlu",
            text="What is the status of project Nexus?"
        )
    except Exception as e:
        print("Agent failed to start due to key issue.")

