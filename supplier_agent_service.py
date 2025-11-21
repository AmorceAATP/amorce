# --- SUPPLIER AGENT SERVICE (Agent B - "MasterTicket") ---
# Role: The "Seller" Brain. It manages inventory and negotiates price via Gemini.
# Deployed on: Cloud Run (as a separate service)
# Language: English (Commercial V1.0)

import os
import json
import logging
import uvicorn
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
import google.generativeai as genai

# --- CONFIGURATION ---
# This service has its own Gemini Key (Brain B)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Real-time Inventory Simulation
INVENTORY = {
    "radiohead_mtl_2026": {
        "name": "Radiohead - Bell Center Montreal - Oct 12 2026",
        "base_price": 250.00,  # Public listing price
        "floor_price": 220.00,  # Secret reserve price
        "stock": 4
    }
}

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="MasterTicket Agent (Supplier B)")


# --- AI BRAIN (GEMINI) ---
def ask_gemini_negotiator(user_offer: float, product: dict) -> dict:
    """
    The AI decides whether to accept the offer or counter-bid.
    """
    # Fallback logic if no AI key is present
    if not GOOGLE_API_KEY:
        if user_offer >= product["base_price"]:
            return {
                "status": "ACCEPTED",
                "final_price": product["base_price"],
                "message": "Standard price accepted. Proceeding to checkout."
            }
        return {
            "status": "COUNTER",
            "final_price": product["base_price"],
            "message": f"I cannot go lower than {product['base_price']}$. This is a high-demand event."
        }

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    prompt = f"""
    You are "MasterTicket Agent", a smart and tough but polite ticket seller.

    PRODUCT CONTEXT:
    - Name: {product['name']}
    - Listed Price: {product['base_price']}$
    - Secret Floor Price: {product['floor_price']}$

    BUYER OFFER: {user_offer}$

    YOUR RULES:
    1. If offer >= {product['base_price']}, ACCEPT immediately.
    2. If offer is between {product['floor_price']} and {product['base_price']}, you CAN accept but try to negotiate a bit higher first (e.g., "Let's meet at X$").
    3. If offer < {product['floor_price']}, REJECT politely and make a counter-offer at {product['base_price'] - 10}$. NEVER go below the Floor Price.
    4. Be concise (one sentence).

    REQUIRED JSON RESPONSE FORMAT (Strict):
    {{
        "status": "ACCEPTED" or "COUNTER" or "REJECTED",
        "price": <final_proposed_price_float>,
        "message": "<your_verbal_response_in_english>"
    }}
    """

    try:
        response = model.generate_content(prompt)
        # Basic markdown JSON cleanup
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        # In production, use json.loads(clean_json) with error handling
        return json.loads(clean_json)
    except Exception as e:
        logging.error(f"Gemini Negotiation Error: {e}")
        # Fail-safe response
        return {
            "status": "COUNTER",
            "price": product["base_price"],
            "message": "I am currently unable to process discounts. Listed price applies."
        }


# --- API ENDPOINTS ---

@app.get("/")
def root():
    return {"agent": "MasterTicket Supplier", "status": "online", "version": "1.0"}


@app.get("/api/v1/products/search")
def search_products(