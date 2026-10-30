import requests


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


def get_weather_forecast(place: str, days: int = 7):
    """Get a daily weather forecast for a place."""
    loc = get_coordinates(place)
    if loc is None:
        return {"error": f"Could not find location: {place}"}

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
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


if __name__ == "__main__":
    print(get_weather_forecast("Rourkela", days=3))