import os
import json
import logging
import requests
import base64  # <-- PHASE 4 IMPORT
from pathlib import Path
from typing import Dict, Any, Optional
import time  # <-- PHASE 4 IMPORT (for timestamp)

# We import the required cryptography dependencies
# For a Zero-Trust agent, this library is essential for Ed25519
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization  # <-- PHASE 4 IMPORT
from cryptography.exceptions import InvalidSignature

# --- Global Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class AgentClient:
    """
    The 'Brain' of the Agent. Manages private key initialization,
    the LLM logic (simulated here), and task signing.
    Now also handles registration with the Trust Directory (Phase 3).
    """

    def __init__(self):
        """Initializes the client and loads Zero-Trust assets."""
        logging.info("Initializing Agent Client (The Brain)...")

        # 1. Load Trust Assets (Keys)
        private_key_pem = os.environ.get("AGENT_PRIVATE_KEY")
        if not private_key_pem:
            logging.error("FATAL: AGENT_PRIVATE_KEY environment variable not set.")
            raise EnvironmentError("AGENT_PRIVATE_KEY must be set for signing.")

        # --- PHASE 4: Load the actual key object ---
        try:
            # We load the private key from the PEM string stored in the env var
            self.agent_private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None  # Assuming no password
            )
            logging.info("Agent Private Key object loaded successfully.")
        except Exception as e:
            logging.error(f"FATAL: Could not parse AGENT_PRIVATE_KEY PEM: {e}")
            raise

        # We still need the PEM string of the public key to *publish* it
        self.agent_public_key_pem = os.environ.get("AGENT_PUBLIC_KEY")
        if not self.agent_public_key_pem:
            logging.error("FATAL: AGENT_PUBLIC_KEY environment variable not set.")
            raise EnvironmentError("AGENT_PUBLIC_KEY must be set for directory registration.")

        # 2. Load Model Access Key (LLM)
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not self.gemini_api_key:
            logging.error("FATAL: GEMINI_API_KEY environment variable not set.")
            raise EnvironmentError("GEMINI_API_KEY must be set for LLM access.")

        # 3. Load Manifest and Agent ID (Phase 2)
        self.manifest = self._load_manifest_locally()
        self.agent_id = self.manifest.get("agent_id", "unknown_agent")
        logging.info(f"Agent ID configured: {self.agent_id}")

        # 4. Load Trust Directory URL (Phase 3)
        self.trust_directory_url = os.environ.get("TRUST_DIRECTORY_URL")
        if not self.trust_directory_url:
            logging.warning("TRUST_DIRECTORY_URL not set. Skipping directory registration.")
        else:
            # This is the new call to publish our identity on startup
            self._register_with_trust_directory()

    def _load_manifest_locally(self) -> Dict[str, Any]:
        """Loads the manifest from disk (used to retrieve the agent_id)."""
        try:
            manifest_path = Path(__file__).parent / "agent-manifest.json"
            with manifest_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"FATAL: Could not load manifest locally: {e}")
            raise

    def _register_with_trust_directory(self):
        """
        PHASE 3: Publishes this agent's identity and public key to the
        central Trust Directory on startup.
        """
        if not self.trust_directory_url:
            return  # Should not happen if called from __init__

        logging.info(f"Registering agent {self.agent_id} with Trust Directory at {self.trust_directory_url}...")

        endpoint = f"{self.trust_directory_url}/api/v1/register"
        payload = {
            "agent_id": self.agent_id,
            "public_key": self.agent_public_key_pem,  # Send the PEM string
            "algorithm": "Ed25519"  # From our manifest
        }

        try:
            response = requests.post(endpoint, json=payload, timeout=5)

            if response.status_code == 200 or response.status_code == 201:
                logging.info(
                    f"Successfully registered/updated identity in Trust Directory: {response.json().get('message')}")
            else:
                logging.error(
                    f"Failed to register with Trust Directory. Status: {response.status_code}, Body: {response.text}")

        except requests.exceptions.RequestException as e:
            logging.error(f"Could not connect to Trust Directory at {endpoint}: {e}")

    def _sign_task(self, task_data: Dict[str, Any]) -> str:
        """
        PHASE 4: Generates a real cryptographic Ed25519 signature.
        The signature is Base64-encoded.
        """
        try:
            # 1. Canonicalize the task data to ensure consistent signatures
            # We sort keys to ensure the JSON string is always the same.
            # separators=(',', ':') removes whitespace.
            canonical_task = json.dumps(task_data, sort_keys=True, separators=(',', ':'))
            task_bytes = canonical_task.encode('utf-8')
            logging.info(f"Signing canonical task: {canonical_task}")

            # 2. Sign the bytes with the loaded private key
            signature_bytes = self.agent_private_key.sign(task_bytes)

            # 3. Encode the signature in Base64 for clean JSON transport
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

            return signature_b64

        except Exception as e:
            logging.error(f"Error during task signing: {e}", exc_info=True)
            # Return a clearly invalid signature on failure
            return "signing_error:could_not_generate_signature"

    def process_chat_turn(self, user_input: str, conversation_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main function. Handles NLU, NLG, and returns the signed task.
        """
        logging.info(f"Processing turn for Agent ID {self.agent_id} with input: {user_input}")

        # --- Step 1: LLM Logic (Simulated) ---
        # (Mocking)

        # --- Step 2: Task Creation ---
        # Based on the NLU, we create the task to be signed.
        task_data = {
            "task_name": "CHAT_TURN_RESPONSE",
            "message": f"Acknowledged. Agent {self.agent_id} is online and processing.",
            "agent_id": self.agent_id,  # **PHASE 2 UPDATE**
            "timestamp": int(time.time())  # PHASE 4: Use a real timestamp
        }

        # --- Step 3: Task Signing (PHASE 4 - REAL) ---
        signature = self._sign_task(task_data)

        # --- Step 4: ATP Response Construction ---
        signed_response = {
            "new_state": conversation_state,
            "response_text": "I am unable to process that specific request at this time, but I am online and ready.",
            "signed_task": {
                "task": task_data,
                "signature": signature,
                "algorithm": "Ed25519"
            }
        }
        return signed_response


# --- Entry Point (Not executed by the Orchestrator, but for testing) ---
if __name__ == '__main__':
    """
    Allows for local testing of this client without running the Flask orchestrator.
    """
    try:
        # We must generate a real key pair for testing
        pk = ed25519.Ed25519PrivateKey.generate()
        priv_key_pem = pk.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        pub_key_pem = pk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        # Set mock environment variables
        os.environ["AGENT_PRIVATE_KEY"] = priv_key_pem
        os.environ["AGENT_PUBLIC_KEY"] = pub_key_pem
        os.environ["GEMINI_API_KEY"] = "mock_gemini_key_for_local_test"
        os.environ["TRUST_DIRECTORY_URL"] = "http://127.0.0.1:9000"  # Mock URL

        client = AgentClient()
        test_response = client.process_chat_turn("Hello, what is your name?", {"user_name": "Robert"})

        logging.info("--- Test Run Successful ---")
        print(json.dumps(test_response, indent=2))

    except EnvironmentError as e:
        logging.critical(f"Client Test Failed: {e}")
    except Exception as e:
        logging.critical(f"A general error occurred during test run: {e}", exc_info=True)

