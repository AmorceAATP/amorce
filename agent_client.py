# --- AGENT CLIENT (AC) v3.1 (Secured) ---
# Implements Athena's Briefing Task 2: Cryptographic task signing.
# Security Audit Fix (v3.1): Strict environment variable enforcement.
# This client handles the core conversation logic (NLU, NLG, Memory)
# and cryptographically signs all outgoing tasks.

import google.generativeai as genai
import json
import os
import re
import base64

# --- DEPENDENCIES ---
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.exceptions import InvalidSignature


# --- 1. CONFIGURATION (SECURED) ---

def get_env_var(name):
    """
    Security Helper: Retrieves an environment variable or raises a fatal error.
    Prevents the agent from running with missing secrets.
    """
    val = os.environ.get(name)
    if not val:
        raise ValueError(f"Security Error: Environment variable {name} is not set.")
    return val


try:
    # LLM API Key
    GOOGLE_API_KEY = get_env_var("GEMINI_API_KEY")
    genai.configure(api_key=GOOGLE_API_KEY)

    # --- AGENT'S PRIVATE KEY (for signing) ---
    AGENT_PRIVATE_KEY_PEM = get_env_var("AGENT_PRIVATE_KEY")

    # Load the PEM-formatted private key
    # Ed25519 keys do not require a password
    AGENT_PRIVATE_KEY = load_pem_private_key(
        AGENT_PRIVATE_KEY_PEM.encode('utf-8'),
        password=None
    )

    print("--- CONFIGURATION SUCCESS: Keys loaded securely. ---")

except Exception as e:
    print(f"--- CONFIGURATION ERROR ---")
    print(f"Error: {e}")
    print("Please ensure GEMINI_API_KEY and AGENT_PRIVATE_KEY are set in your environment.")
    exit(1)  # Fail fast

# --- v3.0: TWO BRAINS (NLU and NLG) ---

# --- NLU BRAIN (Phase 0) ---
NLU_SYSTEM_PROMPT = """
You are an expert NLU (Natural Language Understanding) agent for a travel agency.
Your sole task is to update a JSON object based on the user's request.
Respond with NOTHING but the final JSON.

You will receive:
1.  "Previous JSON State": The state of the conversation (can be empty {}).
2.  "Current User Request": What the user just said.

Your rules:
- Identify the user's intent: 'SEARCH_FLIGHT', 'SEARCH_HOTEL', 'BOOK_ITEM', or 'CLARIFICATION'.
- If the request is a *new* search (e.g., "Find me a hotel in Paris"),
  ignore the previous state and create a NEW, complete JSON for this intent.
- If the user request is a *response* (e.g., "From Paris", "on Dec 15th"),
  USE the previous JSON state and ONLY ADD or MODIFY the information provided. The intent should be 'CLARIFICATION' or the one from the previous state.
- If the user confirms a booking (e.g., "yes", "book it", "that's perfect, confirm"),
  detect the 'BOOK_ITEM' intent.
- Always report the booking_context from the previous state.

Output JSON Structure:
{
  "intent": "SEARCH_FLIGHT" | "SEARCH_HOTEL" | "BOOK_ITEM" | "CLARIFICATION",
  "parameters": {
    "location": "CITY" (or null),
    "departure_date": "YYYY-MM-DD" (or null),
    "origin": "CITY_OR_IATA_CODE" (or null),
    "destination": "CITY_OR_IATA_CODE" (or null),
    "check_in_date": "YYYY-MM-DD" (or null),
    "check_out_date": "YYYY-MM-DD" (or null)
  },
  "booking_context": {
    "item_to_book": { "type": "flight" | "hotel" | null, "id": "ITEM_ID", "price": 123.45 },
    "is_confirmed": false
  }
}
"""

nlu_generation_config = {
    "temperature": 0.0,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

MODEL_NAME_TO_USE = "gemini-2.5-flash"

# NLU Model Initialization
llm_nlu = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlu_generation_config,
    system_instruction=NLU_SYSTEM_PROMPT
)

# --- NLG BRAIN (Phase 2) ---
NLG_SYSTEM_PROMPT = """
You are a conversational, friendly, and helpful travel agent.
Your task is to respond to the user based on the context provided.

- Always be friendly and use a natural, engaging tone.
- If the conversation state is incomplete, politely ask for the missing single piece of information.

- If 'task_results' contains an error (e.g., {"error": "NO_RESULTS"}):
    - Acknowledge the search but apologize for the lack of results.
    - If the error is 'NO_RESULTS', suggest searching again with a slightly different query or date.
    - If the error is 'SERVICE_ERROR', apologize and suggest retrying later or choosing an alternative service.

- If 'task_results' contains successful results (e.g., flight at 650 EUR):
    - Present the best result clearly.
    - ALWAYS finish by asking a confirmation question to book it.
    - (Example: "I found an Air France flight for 650€. Would you like me to book it?")

- If a booking was just confirmed (task_results status is "BOOKING_CONFIRMED"):
    - Confirm the booking to the user and include the confirmation code.
    - (Example: "It's done! Your flight to Montreal is confirmed. Your code is XYZ123.")
"""

nlg_generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

# NLG Model Initialization
llm_nlg = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlg_generation_config,
    system_instruction=NLG_SYSTEM_PROMPT
)


# --- 2. AGENT FUNCTIONS ---

def clean_json_string(s):
    """
    Cleans the raw LLM output to keep only the valid JSON.
    """
    start_index = s.find('{')
    end_index = s.rfind('}')

    if start_index != -1 and end_index != -1 and end_index > start_index:
        return s[start_index:end_index + 1]

    print(f"--- NLU WARNING: Could not clean JSON ---")
    print(f"Raw Response: {s}")
    return None


# --- TASK SIGNING FUNCTION (Task 2) ---
def _sign_task(task_object):
    """
    Signs a task object using the agent's private key (Ed25519)
    and returns it in the new Zero-Trust format.
    """
    if not task_object:
        return None

    try:
        # 1. Serialize the task object into a canonical JSON string.
        # sort_keys=True ensures the key order is always the same.
        # separators=(',', ':') removes whitespace for a compact representation.
        # This is CRITICAL for a consistent signature.
        task_json = json.dumps(task_object, sort_keys=True, separators=(',', ':')).encode('utf-8')

        # 2. Sign the serialized JSON bytes using the loaded private key
        signature = AGENT_PRIVATE_KEY.sign(task_json)

        # 3. Encode the binary signature in Base64 for safe JSON transport
        signature_b64 = base64.b64encode(signature).decode('utf-8')

        # 4. Wrap the original task and signature in the new format
        signed_task_wrapper = {
            "task": task_object,
            "signature": signature_b64,
            "algorithm": "Ed25519"  # As specified in the brief
        }

        print(f"--- INFO: Task successfully signed (Sig: {signature_b64[:10]}...) ---")
        return signed_task_wrapper

    except Exception as e:
        print(f"--- CRITICAL SIGNING ERROR ---")
        print(f"Failed to sign task: {e}")
        # If signing fails, we must not send the task.
        return None


def nlu_phase_llm(user_prompt, previous_state):
    """
    Phase 0: NLU (Natural Language Understanding) - v3.0
    """
    print("--- 0. NLU PHASE (v3.0 NLU Brain) ---")
    print(f"User prompt: \"{user_prompt}\"")

    nlu_context = f"""
    Previous JSON State:
    {json.dumps(previous_state, indent=2)}
    Current User Request:
    "{user_prompt}"
    Updated JSON:
    """

    print(f"Contacting Gemini API (NLU) with model '{MODEL_NAME_TO_USE}'...")

    try:
        response = llm_nlu.generate_content(nlu_context)
        raw_text = response.text
    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during NLU Phase ---")
        print(f"Error: {e}")
        return previous_state

    json_string = clean_json_string(raw_text)
    if not json_string:
        print(f"--- NLU ERROR: Non-JSON or malformed response received ---")
        print(f"Raw Response: {raw_text}")
        return previous_state

    try:
        updated_state = json.loads(json_string)

        # Persistence logic for the booking context
        if previous_state.get("booking_context", {}).get("item_to_book") and \
                not updated_state.get("booking_context", {}).get("item_to_book") and \
                updated_state.get("intent") != "BOOK_ITEM":
            print("--- INFO: Manually reporting 'item_to_book' in state.")
            if "booking_context" not in updated_state:
                updated_state["booking_context"] = {}
            updated_state["booking_context"]["item_to_book"] = previous_state["booking_context"]["item_to_book"]

        print("Intent successfully updated:")
        print(json.dumps(updated_state, indent=2))
        return updated_state
    except json.JSONDecodeError:
        print(f"--- NLU ERROR: Invalid JSON after cleanup ---")
        print(f"Cleaned JSON (attempt): {json_string}")
        return previous_state


def core_processing_phase(conversation_state):
    """
    Phase 1: Core Processing (Task Preparation