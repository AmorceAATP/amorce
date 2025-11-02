import os
import json
import logging
import requests  # <-- PHASE 3 IMPORT
from pathlib import Path
from typing import Dict, Any, Optional

# We import the required cryptography dependencies
# For a Zero-Trust agent, this library is essential for Ed25519
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
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
        self.agent_private_key = os.environ.get("AGENT_PRIVATE_KEY")
        if not self.agent_private_key:
            logging.error("FATAL: AGENT_PRIVATE_KEY environment variable not set.")
            raise EnvironmentError("AGENT_PRIVATE_KEY must be set for signing.")

        # PHASE 3: Load Public Key to publish it
        self.agent_public_key = os.environ.get("AGENT_PUBLIC_KEY")
        if not self.agent_public_key:
            logging.error("FATAL: AGENT_PUBLIC_KEY environment variable not set.")
            raise EnvironmentError("AGENT_PUBLIC_KEY must be set for directory registration.")

        logging.info("Agent Private & Public Keys loaded successfully (Simulated).")

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

        endpoint = f"{self.trust_directory_url}/register"
        payload = {
            "agent_id": self.agent_id,
            "public_key": self.agent_public_key,
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
        Generates the cryptographic Ed25519 signature of the task.
        This implementation is simulated (Phase 1).
        """
        # In production:
        # 1. task_data would be serialized into a canonical format (e.g., sorted JSON).
        # 2. task_bytes = canonical_json_dump(task_data).encode('utf-8')
        # 3. signature = self.private_key.sign(task_bytes)

        # Simulation:
        return f"mock_signature_for_{self.agent_id}_agent"

    def process_chat_turn(self, user_input: str, conversation_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main function. Handles NLU, NLG, and returns the signed task.
        """
        logging.info(f"Processing turn for Agent ID {self.agent_id} with input: {user_input}")

        # --- Step 1: LLM Logic (Simulated) ---
        # The actual code would call the Gemini API here.
        # NLU_result = self._call_llm_for_nlu(user_input, self.manifest)

        # --- Step 2: Task Creation ---
        # Based on the NLU, we create the task to be signed.
        task_data = {
            "task_name": "CHAT_TURN_RESPONSE",
            "message": f"Acknowledged. Agent {self.agent_id} is online and processing.",
            "agent_id": self.agent_id,  # **PHASE 2 UPDATE**
            "timestamp": "2025-11-01T20:00:00Z"
        }

        # --- Step 3: Task Signing ---
        signature = self._sign_task(task_data)

        # --- Step 4: ATP Response Construction ---
        mock_signed_response = {
            "new_state": conversation_state,
            "response_text": "I am unable to process that specific request at this time, but I am online and ready.",
            "signed_task": {
                "task": task_data,
                "signature": signature,
                "algorithm": "Ed25519"
            }
        }
        return mock_signed_response


# --- Entry Point (Not executed by the Orchestrator, but for testing) ---
if __name__ == '__main__':
    try:
        # For testing, we must set the new env vars
        os.environ["AGENT_PUBLIC_KEY"] = "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
        os.environ["TRUST_DIRECTORY_URL"] = "http://127.0.0.1:9000"  # Mock URL

        client = AgentClient()
        test_response = client.process_chat_turn("Hello, what is your name?", {"user_name": "Robert"})
        logging.info("Test Run Successful.")
        print(json.dumps(test_response, indent=2))

    except EnvironmentError as e:
        logging.critical(f"Client Test Failed: {e}")

