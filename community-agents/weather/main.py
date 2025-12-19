"""
Amorce Weather Agent

A community agent that wraps the Open-Meteo API to provide weather data.
Uses the Amorce protocol for secure agent-to-agent communication.

Open-Meteo: https://open-meteo.com/ (free, no API key required)
"""

import os
import json
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import nacl.signing
import nacl.encoding
import base64

app = FastAPI(
    title="Weather Agent",
    description="Amorce-compatible weather agent using Open-Meteo API",
    version="1.0.0"
)

# Agent configuration
AGENT_ID = os.environ.get("AGENT_ID", "weather-agent")
AGENT_NAME = "Weather Agent"
AGENT_DESCRIPTION = "Get current weather and forecasts for any location worldwide"
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT", "https://weather.agents.amorce.io")

# Load or generate keys
PRIVATE_KEY_PATH = os.environ.get("PRIVATE_KEY_PATH", "agent_private_key.pem")
PUBLIC_KEY_PATH = os.environ.get("PUBLIC_KEY_PATH", "agent_public_key.pem")

# Open-Meteo API base URL
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def load_or_generate_keys():
    """Load existing keys or generate new ones."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = nacl.signing.SigningKey(f.read())
        with open(PUBLIC_KEY_PATH, 'rb') as f:
            public_key_bytes = f.read()
    except FileNotFoundError:
        # Generate new keys
        private_key = nacl.signing.SigningKey.generate()
        public_key_bytes = private_key.verify_key.encode()
        
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(private_key.encode())
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(public_key_bytes)
    
    return private_key, base64.b64encode(public_key_bytes).decode()


SIGNING_KEY, PUBLIC_KEY_B64 = load_or_generate_keys()


# Request/Response models
class WeatherRequest(BaseModel):
    latitude: float
    longitude: float
    

class ForecastRequest(BaseModel):
    latitude: float
    longitude: float
    days: int = 7


class WeatherResponse(BaseModel):
    temperature: float
    temperature_unit: str
    conditions: str
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_unit: str = "km/h"
    location: dict


class ForecastDay(BaseModel):
    date: str
    high: float
    low: float
    conditions: str
    precipitation_probability: Optional[float] = None


class ForecastResponse(BaseModel):
    location: dict
    days: List[ForecastDay]


# Weather code to conditions mapping
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy", 
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_conditions(weather_code: int) -> str:
    """Convert weather code to human-readable conditions."""
    return WEATHER_CODES.get(weather_code, "Unknown")


# ============================================================
# .well-known/agent.json - A2A Protocol Discovery
# ============================================================

@app.get("/.well-known/agent.json")
async def agent_manifest():
    """Return A2A-compatible agent manifest for discovery."""
    return {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "url": AGENT_ENDPOINT,
        "version": "1.0.0",
        "protocol": "amorce-a2a",
        "publicKey": PUBLIC_KEY_B64,
        "capabilities": ["get_weather", "get_forecast"],
        "skills": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "latitude": {"type": "number", "description": "Latitude (-90 to 90)"},
                        "longitude": {"type": "number", "description": "Longitude (-180 to 180)"}
                    },
                    "required": ["latitude", "longitude"]
                }
            },
            {
                "name": "get_forecast",
                "description": "Get weather forecast for upcoming days",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                        "days": {"type": "integer", "default": 7, "maximum": 16}
                    },
                    "required": ["latitude", "longitude"]
                }
            }
        ],
        "provider": {
            "name": "Amorce Community",
            "url": "https://amorce.io"
        },
        "discoverable": True
    }


# ============================================================
# Agent Capabilities
# ============================================================

@app.post("/capabilities/get_weather")
async def get_weather(request: WeatherRequest):
    """Get current weather for a location."""
    params = {
        "latitude": request.latitude,
        "longitude": request.longitude,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        "timezone": "auto"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        data = response.json()
    
    current = data.get("current", {})
    
    return WeatherResponse(
        temperature=current.get("temperature_2m", 0),
        temperature_unit="°C",
        conditions=get_conditions(current.get("weather_code", 0)),
        humidity=current.get("relative_humidity_2m"),
        wind_speed=current.get("wind_speed_10m"),
        wind_unit="km/h",
        location={
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timezone": data.get("timezone")
        }
    )


@app.post("/capabilities/get_forecast")
async def get_forecast(request: ForecastRequest):
    """Get weather forecast for upcoming days."""
    params = {
        "latitude": request.latitude,
        "longitude": request.longitude,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": min(request.days, 16)
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        data = response.json()
    
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    codes = daily.get("weather_code", [])
    precip = daily.get("precipitation_probability_max", [])
    
    days = []
    for i in range(len(dates)):
        days.append(ForecastDay(
            date=dates[i],
            high=highs[i] if i < len(highs) else 0,
            low=lows[i] if i < len(lows) else 0,
            conditions=get_conditions(codes[i] if i < len(codes) else 0),
            precipitation_probability=precip[i] if i < len(precip) else None
        ))
    
    return ForecastResponse(
        location={
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timezone": data.get("timezone")
        },
        days=days
    )


# ============================================================
# Amorce Protocol Endpoint
# ============================================================

@app.post("/agent")
async def agent_endpoint(request: Request):
    """
    Main Amorce protocol endpoint.
    Handles signed requests from other agents.
    """
    try:
        body = await request.json()
        
        # Extract capability and params
        capability = body.get("capability")
        params = body.get("params", {})
        
        # Route to capability
        if capability == "get_weather":
            result = await get_weather(WeatherRequest(**params))
        elif capability == "get_forecast":
            result = await get_forecast(ForecastRequest(**params))
        else:
            return JSONResponse(
                {"error": f"Unknown capability: {capability}"},
                status_code=400
            )
        
        # Sign response
        response_data = result.model_dump() if hasattr(result, 'model_dump') else result
        response_json = json.dumps(response_data, sort_keys=True)
        signature = SIGNING_KEY.sign(response_json.encode()).signature
        
        return JSONResponse({
            "result": response_data,
            "signature": base64.b64encode(signature).decode(),
            "agent_id": AGENT_ID
        })
        
    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


# ============================================================
# Health & Info
# ============================================================

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": AGENT_NAME}


@app.get("/")
async def root():
    return {
        "agent": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "capabilities": ["get_weather", "get_forecast"],
        "docs": "/docs",
        "manifest": "/.well-known/agent.json"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
