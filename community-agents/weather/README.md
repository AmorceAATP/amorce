# Weather Agent

An Amorce-compatible agent that provides weather data via the Open-Meteo API.

## Features

- **No API key required** - Uses Open-Meteo free API
- **A2A Protocol compliant** - Publishes `/.well-known/agent.json`
- **Signed responses** - Ed25519 signatures for trust

## Capabilities

| Capability | Description |
|------------|-------------|
| `get_weather` | Get current weather for lat/long |
| `get_forecast` | Get 7-day forecast for lat/long |

## Usage

### Direct HTTP

```bash
# Get current weather for New York
curl -X POST http://localhost:8080/capabilities/get_weather \
  -H "Content-Type: application/json" \
  -d '{"latitude": 40.7128, "longitude": -74.0060}'

# Get 7-day forecast
curl -X POST http://localhost:8080/capabilities/get_forecast \
  -H "Content-Type: application/json" \
  -d '{"latitude": 40.7128, "longitude": -74.0060, "days": 7}'
```

### Via Amorce Protocol

```python
from amorce_sdk import AmorceClient

client = AmorceClient()
weather = await client.call_agent(
    agent_id="weather-agent",
    capability="get_weather",
    params={"latitude": 40.7128, "longitude": -74.0060}
)
```

## Local Development

```bash
pip install -r requirements.txt
python main.py
```

## Deploy to Cloud Run

```bash
gcloud run deploy weather-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## Data Source

Weather data provided by [Open-Meteo](https://open-meteo.com/) - free, open-source weather API.
