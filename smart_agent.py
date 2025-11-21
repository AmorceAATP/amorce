"""
SMART AGENT (ATP v3.1 - Secured)
Refactored to use Nexus SDK and enforced configuration security.
"""

import os
import json
import uuid
import logging
from typing import Dict, Any
from nexus import NexusClient, IdentityManager, GoogleSecretManagerProvider
from pydantic import BaseModel, Field
import google.generativeai as genai

# --- Application Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("smart_agent")

# --- Configuration (Security Fix: No Hardcoded Defaults) ---
TRUST_DIRECTORY_URL = os.environ.get("TRUST_DIRECTORY_URL", "https://amorce-trust-api-425870997313.us-central1.run.app")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "https://amorce-api-425870997313.us-central1.run.app")

AGENT_ID = os.environ.get("AGENT_ID")
AGENT_API_KEY = os.environ.get("AGENT_API_KEY")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
SECRET_NAME = os.environ.get("SECRET_NAME")

# Fail fast if critical config is missing
if not all([AGENT_ID, AGENT_API_KEY, GCP_PROJECT_ID, SECRET_NAME]):
    logger.critical("SECURITY ERROR: Missing required environment variables (AGENT_ID, AGENT_API_KEY, GCP_PROJECT_ID, SECRET_NAME).")
    logger.critical("Hardcoded defaults have been removed for security.")
    exit(1)

# Initialize Gemini
try:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")
    genai.configure(api_key=GOOGLE_API_KEY)

    GEMINI_SYSTEM_PROMPT_CLIENT = (
        "You are a purchasing agent. Your high-level goal is: [GOAL]. "
        "The conversation history with the seller is: [HISTORY]. "
        "Based on this, decide the *next message* to send to the seller. "
        "Keep your messages concise. "
        "If the seller's last message confirms the purchase, just respond with 'TERMINATE'. "
        "If the seller makes an acceptable offer, respond with a message to confirm the purchase."
    )

    gemini_client_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-preview-09-2025",
        system_instruction=GEMINI_SYSTEM_PROMPT_CLIENT
    )
    logger.info("Agent A (Client) Gemini brain initialized.")
except Exception as e:
    logger.error(f"FATAL: Could not initialize Agent A's Gemini brain: {e}")
    exit(1)


# --- Conversation Protocol ---
class ConversationTurn(BaseModel):
    session_id: str = Field(..., description="The unique ID linking all turns.")
    turn_id: int = Field(..., description="The sequential order of the turn.")
    role: str = Field(..., description="The sender ('client' or 'provider').")
    content: str = Field(..., description="The natural language message.")
    status: str = Field(..., description="INITIATE, AWAIT_RESPONSE, TERMINATED.")


def main():
    try:
        # 1. Initialize Identity (SDK)
        logger.info("Initializing Identity Provider...")
        provider = GoogleSecretManagerProvider(
            project_id=GCP_PROJECT_ID,
            secret_name=SECRET_NAME
        )
        identity = IdentityManager(provider)
        logger.info(f"Identity loaded for public key: {identity.public_key_pem[:30]}...")

        # 2. Initialize Client (SDK)
        client = NexusClient(
            identity=identity,
            directory_url=TRUST_DIRECTORY_URL,
            orchestrator_url=ORCHESTRATOR_URL,
            agent_id=AGENT_ID,
            api_key=AGENT_API_KEY
        )

        # 3. Discover Service (SDK)
        logger.info("Discovering services...")
        services = client.discover("product_negotiator")
        if not services:
            logger.error("No services found.")
            return

        service_to_use = services[0]
        logger.info(f"Service found: {service_to_use.get('service_id')}")

        # 4. Run Conversation Loop
        HIGH_LEVEL_GOAL = "I need to buy one 'product xyz'. Negotiate the best price you can, but do not exceed $20."
        run_ai_conversation_loop(client, service_to_use, HIGH_LEVEL_GOAL)

    except Exception as e:
        logger.critical(f"Agent crashed: {e}")

def run_ai_conversation_loop(client: NexusClient, service_contract: Dict[str, Any], high_level_goal: str):
    logger.info(f"Starting autonomous negotiation. Goal: {high_level_goal}")

    session_id = str(uuid.uuid4())
    turn_counter = 1
    conversation_history = []

    while True:
        # Brain Logic
        formatted_history = [f"{t['role']}: {t['content']}" for t in conversation_history]
        prompt = GEMINI_SYSTEM_PROMPT_CLIENT.replace("[GOAL]", high_level_goal)
        prompt = prompt.replace("[HISTORY]", json.dumps(formatted_history))

        try:
            response = gemini_client_model.generate_content(prompt)
            ai_message = response.text
            logger.info(f"[Me]: {ai_message}")
        except Exception as e:
            logger.error(f"Brain freeze: {e}")
            break

        if "TERMINATE" in ai_message:
            logger.info("Agent decided to terminate.")
            break

        # Protocol Logic
        turn_obj = ConversationTurn(
            session_id=session_id,
            turn_id=turn_counter,
            role="client",
            content=ai_message,
            status="INITIATE" if turn_counter == 1 else "AWAIT_RESPONSE"
        )
        conversation_history.append(turn_obj.model_dump(mode='json'))

        # Transport Logic
        logger.info(f"Sending turn {turn_counter}...")
        tx_response = client.transact(
            service_contract=service_contract,
            payload=turn_obj.model_dump(mode='json')
        )

        if not tx_response:
            logger.error("Transaction failed.")
            break

        if tx_response.get("error"):
             logger.error(f"Transaction returned error: {tx_response.get('error')}")
             break

        result = tx_response.get("result")
        if not result:
             logger.error(f"Empty result from provider: {tx_response}")
             break

        try:
            provider_turn = ConversationTurn(**result)
            logger.info(f"[Provider]: {provider_turn.content}")
            conversation_history.append(provider_turn.model_dump(mode='json'))

            if provider_turn.status == "TERMINATED":
                logger.info("Provider terminated the session.")
                break

            turn_counter = provider_turn.turn_id + 1

            if turn_counter > 10:
                logger.warning("Safety limit reached.")
                break

        except Exception as e:
            logger.error(f"Failed to parse provider response: {e}")
            break


def run_bridge_transaction(service_id: str, payload: dict) -> dict:
    """
    (FR-O1) Bridge Logic: Called by the Orchestrator to execute a transaction
    on behalf of a No-Code tool.
    1. Builds the P-6 Transaction Body.
    2. Signs it with the Managed Key (L2).
    3. Sends it to the Orchestrator (A2A).
    """
    print(f"BRIDGE: Building transaction for service_id: {service_id}")

    # 1. Build Transaction
    body = {
        "transaction_id": str(uuid4()),
        "service_id": service_id,
        "consumer_agent_id": AGENT_ID,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload
    }

    # 2. Sign (L2 Security)
    try:
        signature = sign_message(body)
    except Exception as e:
        return {"error": f"Signing failed: {str(e)}", "status": "failed"}

    headers = {
        "X-Agent-Signature": signature,
        "Content-Type": "application/json",
        "X-API-Key": AGENT_API_KEY
    }

    # 3. Execute (A2A Route)
    try:
        # Loopback call to the Orchestrator
        response = requests.post(ORCHESTRATOR_TRANSACT_URL, json=body, headers=headers, timeout=10)

        # Return the full JSON response (whether success or error)
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"error": response.text, "status": "failed"}

    except requests.exceptions.RequestException as e:
        return {"error": f"Connection failed: {str(e)}", "status": "failed"}
if __name__ == "__main__":
    main()