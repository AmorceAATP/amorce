# --- SMART AGENT (ATP P-7) ---
# This agent implements the "autonomy" phase (P-7).
# It discovers, selects, and then executes a service.

import requests
import os
import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from google.cloud import secretmanager
import base64
import json
from uuid import uuid4
from datetime import datetime, UTC

# --- Configuration (Copied from agent_client.py) ---
TRUST_DIRECTORY_URL = "https://amorce-trust-api-425870997313.us-central1.run.app"
ORCHESTRATOR_TRANSACT_URL = "https://amorce-api-425870997313.us-central1.run.app/v1/a2a/transact"

# P-4: AGENT_ID is our agent's (Agent A) static UUID
AGENT_ID = os.environ.get("AGENT_ID", "e4b0c7c8-4b9f-4b0d-8c1a-2b9d1c9a0c1a")

# L1 Security: API Key for the Orchestrator
AGENT_API_KEY = os.environ.get("AGENT_API_KEY")

# GCP Project ID where the secret is stored.
GCP_PROJECT_ID = "amorce-prod-rgosselin"

# L2 Security: Secret name for our Private Key
SECRET_NAME = "atp-agent-private-key"

# In-memory cache for the private key
_private_key_cache = None


def _get_key_from_secret_manager():
    """
    Fetches the private key from GCP Secret Manager.
    (This logic is identical to agent_client.py)
    """
    global _private_key_cache
    if _private_key_cache:
        return _private_key_cache

    try:
        print(f"Loading private key from Secret Manager: {SECRET_NAME}...")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        pem_data = response.payload.data
        _private_key_cache = serialization.load_pem_private_key(
            pem_data,
            password=None,
            backend=default_backend()
        )
        print("Private key loaded into memory successfully.")
        return _private_key_cache

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load private key: {e}")
        raise


def sign_message(message_body: dict) -> str:
    """
    Signs a message body (dict) using the in-memory Ed25519 private key.
    (This logic is identical to agent_client.py)
    """
    private_key = _get_key_from_secret_manager()
    canonical_message = json.dumps(message_body, sort_keys=True).encode('utf-8')
    signature = private_key.sign(canonical_message)
    return base64.b64encode(signature).decode('utf-8')


# --- P-7: AGENT AUTONOMY LOGIC ---

def discover_service(service_type: str) -> dict:
    """
    (P-7.1) Phase 1 & 2: Discover and Select the service.
    """
    search_url = f"{TRUST_DIRECTORY_URL}/api/v1/services/search"
    print(f"\n--- P-7.1: DISCOVERY ---")
    print(f"Searching for services of type '{service_type}' at {search_url}")

    try:
        # 1. DISCOVERY
        response = requests.get(search_url, params={"service_type": service_type}, timeout=5)
        response.raise_for_status()  # Raise error for 4xx/5xx

        services_list = response.json()

        if not services_list:
            raise Exception(f"No services found matching type '{service_type}'")

        # 2. SELECTION
        # We select the first available service
        selected_service = services_list[0]
        service_id = selected_service.get("service_id")

        if not service_id:
            raise Exception("Service discovery failed: Found service is missing 'service_id'")

        print(f"Discovery complete. Selected service_id: {service_id}")
        return selected_service

    except requests.exceptions.RequestException as e:
        print(f"Service Discovery failed: Could not connect to Trust Directory: {e}")
        raise
    except Exception as e:
        print(f"Service Discovery failed: {e}")
        raise


def execute_transaction(service_contract: dict, payload: dict):
    """
    (P-7.2) Phase 3 & 4: Execute the transaction.
    """
    print("\n--- P-7.2: EXECUTION ---")

    service_id = service_contract.get("service_id")
    print(f"Building transaction for service_id: {service_id}")

    # 3. EXECUTION (Build Transaction)
    body = {
        "transaction_id": str(uuid4()),
        "service_id": service_id,
        "consumer_agent_id": AGENT_ID,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload
    }

    try:
        # Sign the *entire* transaction body (L2)
        signature = sign_message(body)
    except Exception as e:
        print(f"Failed to sign P-7 transaction: {e}")
        return

    headers = {
        "X-Agent-Signature": signature,  # L2 Security
        "Content-Type": "application/json",
        "X-API-Key": AGENT_API_KEY  # L1 Security
    }

    if not AGENT_API_KEY:
        print("CRITICAL: AGENT_API_KEY environment variable not set.")
        return

    # Call the Orchestrator
    try:
        print(f"Sending P-7 A2A request to {ORCHESTRATOR_TRANSACT_URL}...")
        response = requests.post(ORCHESTRATOR_TRANSACT_URL, json=body, headers=headers, timeout=10)

        print(f"\n--- P-7.3: VALIDATION (Status: {response.status_code}) ---")
        print(json.dumps(response.json(), indent=2))

    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to orchestrator (A2A): {e}")


if __name__ == "__main__":
    try:
        # Load key once
        _get_key_from_secret_manager()

        # 1. Discover the "product_retrieval" service
        service_to_use = discover_service(service_type="product_retrieval")

        # 2. Define the payload for that service
        # (This is the only hardcoded part left)
        payload_to_send = {
            "product_id": "1"
        }

        # 3. Execute the transaction
        execute_transaction(service_to_use, payload_to_send)

    except Exception as e:
        print(f"\n--- SMART AGENT FAILED ---")
        print(f"Error: {e}")