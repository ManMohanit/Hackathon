import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
MANDI_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

# In-memory only (never saved to disk): holds live API results for 10 minutes
_cache = {}
CACHE_SECONDS = 600


# ---------------------------------------------------------------------------
# WEATHER TOOL (live: Open-Meteo)
# ---------------------------------------------------------------------------
def get_coordinates(place: str, state: str = ""):
    """Convert a place name to latitude and longitude."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": place, "count": 10, "language": "en", "format": "json"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        return None
    if state:
        for res in results:
            if state.lower() in (res.get("admin1") or "").lower():
                return _loc(res)
    return _loc(results[0])


def _loc(res):
    return {
        "name": res["name"],
        "state": res.get("admin1", ""),
        "lat": res["latitude"],
        "lon": res["longitude"],
    }


def get_weather_forecast(place: str, days: int = 5, state: str = ""):
    """Get a live daily weather forecast for a place."""
    try:
        loc = get_coordinates(place, state)
        if loc is None:
            return {"error": f"Could not find location: {place}"}

        params = {
            "latitude": loc["lat"],
            "longitude": loc["lon"],
            "daily": (
                "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                "precipitation_probability_max,wind_speed_10m_max"
            ),
            "timezone": "auto",
            "forecast_days": days,
        }
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
        r.raise_for_status()
        d = r.json()["daily"]
    except requests.exceptions.RequestException as e:
        return {"error": f"Weather service unavailable: {e}"}

    forecast = []
    for i in range(len(d["time"])):
        forecast.append({
            "date": d["time"][i],
            "max_temp_c": d["temperature_2m_max"][i],
            "min_temp_c": d["temperature_2m_min"][i],
            "rain_mm": d["precipitation_sum"][i],
            "rain_chance_percent": d["precipitation_probability_max"][i],
            "max_wind_kmh": d["wind_speed_10m_max"][i],
        })
    return {
        "source": "live Open-Meteo API",
        "location": f"{loc['name']}, {loc['state']}",
        "forecast": forecast,
    }


# ---------------------------------------------------------------------------
# MANDI PRICE TOOL (live: data.gov.in / Agmarknet)
# ---------------------------------------------------------------------------
def _api_get(extra_params, timeout=20):
    api_key = os.getenv("DATA_GOV_API_KEY")
    if not api_key:
        raise RuntimeError("DATA_GOV_API_KEY is not set")
    params = {"api-key": api_key, "format": "json", **extra_params}
    r = requests.get(MANDI_URL, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json().get("records", [])


def _live_records(state: str):
    """Fetch live records. Tries the state first, then general live pages."""
    key = state.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1], None

    records, last_error = [], None

    # 1) Records for the farmer's state (smaller, faster, more relevant)
    if state:
        try:
            records = _api_get({"limit": 300, "filters[state]": state}, timeout=25)
        except Exception as e:
            last_error = str(e)

    # 2) Otherwise a few pages of the latest records from all states
    if not records:
        for page in range(3):
            try:
                batch = _api_get({"limit": 200, "offset": page * 200}, timeout=20)
            except Exception as e:
                last_error = str(e)
                break
            if not batch:
                break
            records.extend(batch)

    if records:
        _cache[key] = (time.time(), records)
        return records, None
    return None, last_error


def _format(recs):
    return [{
        "market": r.get("market"),
        "district": r.get("district"),
        "state": r.get("state"),
        "commodity": r.get("commodity"),
        "date": r.get("arrival_date"),
        "min_price": r.get("min_price"),
        "max_price": r.get("max_price"),
        "modal_price": r.get("modal_price"),
    } for r in recs]


def get_mandi_prices(commodity: str, state: str = "", limit: int = 5):
    """Get live mandi prices in INR per quintal from data.gov.in.
    If the state has no records for the crop, returns the same crop from
    other states (also live) and says so."""
    records, error = _live_records(state)
    if records is None:
        return {
            "error": "Live mandi price service (data.gov.in) is not responding right now. "
                     f"No price data is available. Details: {error}"
        }

    crop = [r for r in records if commodity.lower() in (r.get("commodity") or "").lower()]
    in_state = [r for r in crop if state and state.lower() in (r.get("state") or "").lower()]

    if in_state:
        return {
            "source": "live data.gov.in (Agmarknet)",
            "commodity": commodity,
            "note": f"Prices from markets in {state}.",
            "prices_per_quintal_inr": _format(in_state[:limit]),
        }

    # Same crop, other states, fetched live from the general feed
    if state:
        try:
            general = []
            for page in range(3):
                batch = _api_get({"limit": 200, "offset": page * 200}, timeout=20)
                if not batch:
                    break
                general.extend(batch)
            crop = [r for r in general if commodity.lower() in (r.get("commodity") or "").lower()]
        except Exception:
            crop = []

    if not crop:
        return {
            "source": "live data.gov.in (Agmarknet)",
            "error": f"No recent price records found for {commodity}.",
        }

    return {
        "source": "live data.gov.in (Agmarknet)",
        "commodity": commodity,
        "note": (
            f"No recent records for {commodity} in {state or 'the requested state'}. "
            "These are live prices from other states, so tell the farmer they are not local."
        ),
        "prices_per_quintal_inr": _format(crop[:limit]),
    }


if __name__ == "__main__":
    print(get_weather_forecast("Rourkela", days=3, state="Odisha"))
    print()
    print(get_mandi_prices("Potato", "Odisha", limit=5))