import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

CACHE_FILE = "sample_mandi.json"


# ---------------------------------------------------------------------------
# WEATHER TOOL
# ---------------------------------------------------------------------------
def get_coordinates(place: str):
    """Convert a place name (village/city) to latitude and longitude."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": place, "count": 1, "language": "en", "format": "json"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    top = results[0]
    return {
        "name": top["name"],
        "state": top.get("admin1", ""),
        "lat": top["latitude"],
        "lon": top["longitude"],
    }


def get_weather_forecast(place: str, days: int = 5):
    """Get a daily weather forecast for a place."""
    loc = get_coordinates(place)
    if loc is None:
        return {"error": f"Could not find location: {place}"}

    url = "https://api.open-meteo.com/v1/forecast"
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
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    d = r.json()["daily"]

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
    return {"location": f"{loc['name']}, {loc['state']}", "forecast": forecast}


# ---------------------------------------------------------------------------
# MANDI PRICE TOOL
# ---------------------------------------------------------------------------
def _fetch_mandi_records():
    """Fetch recent mandi records in small pages. Saves a local cache on success."""
    api_key = os.getenv("DATA_GOV_API_KEY")
    if not api_key:
        return None, "DATA_GOV_API_KEY not found"

    resource_id = "9ef84268-d588-465a-a308-a864a43d0070"
    url = f"https://api.data.gov.in/resource/{resource_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    all_records = []
    last_error = None
    for page in range(2):
        params = {
            "api-key": api_key,
            "format": "json",
            "limit": 200,
            "offset": page * 200,
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            batch = r.json().get("records", [])
            if not batch:
                break
            all_records.extend(batch)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            break

    if all_records:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(all_records, f)
        except OSError:
            pass
        return all_records, None
    return None, last_error


def _load_cached_records():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _format_prices(recs):
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
    """Get recent mandi prices (INR per quintal). If the state has no data,
    falls back to the same crop in other states and says so."""
    records, error = _fetch_mandi_records()
    source = "live data.gov.in"

    if records is None:
        records = _load_cached_records()
        source = "saved sample (live service unavailable)"
        if records is None:
            return {"error": f"Mandi price service is not responding: {error}"}

    crop_matches = [
        r for r in records
        if commodity.lower() in (r.get("commodity") or "").lower()
    ]
    if not crop_matches:
        return {"error": f"No recent price records found for {commodity} ({source})."}

    in_state = [
        r for r in crop_matches
        if state and state.lower() in (r.get("state") or "").lower()
    ]

    if in_state:
        return {
            "commodity": commodity,
            "source": source,
            "note": f"Prices from markets in {state}.",
            "prices_per_quintal_inr": _format_prices(in_state[:limit]),
        }

    return {
        "commodity": commodity,
        "source": source,
        "note": (
            f"No recent price records for {commodity} in {state or 'the requested state'}. "
            "Showing the same crop from other states instead, so tell the farmer these "
            "are not local prices."
        ),
        "prices_per_quintal_inr": _format_prices(crop_matches[:limit]),
    }


if __name__ == "__main__":
    print(get_weather_forecast("Rourkela", days=3))
    print()
    print(get_mandi_prices("Potato", "Odisha", limit=5))