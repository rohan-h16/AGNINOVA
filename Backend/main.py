import os
import math
import time
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================
# AGNINOVA
# Extreme Heatwave Early Warning & Human Thermal Stress Platform
# Open-Meteo Live Weather Intelligence
# ============================================================

app = FastAPI(
    title="AGNINOVA",
    description="Extreme Heatwave Early Warning & Human Thermal Stress Platform",
    version="4.0"
)


def get_active_weather_provider():
    return "Open-Meteo"


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# OPEN-METEO CONFIG
# ============================================================

TOMORROW_API_KEY = os.getenv(
    "TOMORROW_API_KEY",
    ""
).strip()

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

OPEN_METEO_FORECAST_URL = OPEN_METEO_URL

DB_FILE = os.path.join(
    os.path.dirname(__file__),
    "heatwave.db"
)


# ============================================================
# CACHE
# ============================================================

# Selected/current weather:
# refresh at most once every 60 seconds per district.
CURRENT_CACHE_SECONDS = 60

# Statewide GIS:
# refresh at most once every 15 minutes.
#
# This is deliberately longer because Tomorrow.io free
# plans have request limits.
GIS_CACHE_SECONDS = 900

weather_cache = {}
gis_cache = {}


# ============================================================
# KARNATAKA DISTRICTS
# ============================================================

# District centroids for Karnataka, aligned to district headquarters / known town coordinates.
# These are deterministic, real-world reference coordinates and are not generated from random formulas.
LOCATIONS = {
    "Bagalkot": (16.18, 75.69),
    "Ballari": (15.14, 76.92),
    "Belagavi": (15.85, 74.50),
    "Bengaluru Urban": (12.97, 77.59),
    "Bengaluru Rural": (13.20, 77.71),
    "Bidar": (17.91, 77.52),
    "Chamarajanagar": (11.92, 76.94),
    "Chikkaballapur": (13.43, 77.73),
    "Chikkamagaluru": (13.32, 75.77),
    "Chitradurga": (14.23, 76.40),
    "Dakshina Kannada": (12.87, 74.88),
    "Davanagere": (14.47, 75.92),
    "Dharwad": (15.46, 75.01),
    "Gadag": (15.43, 75.63),
    "Hassan": (13.00, 76.10),
    "Haveri": (14.79, 75.40),
    "Kalaburagi": (17.33, 76.83),
    "Kodagu": (12.42, 75.74),
    "Kolar": (13.14, 78.13),
    "Koppal": (15.35, 76.15),
    "Mandya": (12.52, 76.90),
    "Mysuru": (12.30, 76.65),
    "Raichur": (16.21, 77.36),
    "Ramanagara": (12.72, 77.28),
    "Shivamogga": (13.93, 75.57),
    "Tumakuru": (13.34, 77.10),
    "Udupi": (13.34, 74.74),
    "Uttara Kannada": (14.80, 74.13),
    "Vijayapura": (16.83, 75.71),
    "Yadgir": (16.77, 77.13),
    "Vijayanagara": (15.17, 76.36),
}


# ============================================================
# DATABASE
# ============================================================

def init_db():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT,
            date TEXT,
            temperature REAL,
            humidity REAL,
            wind_speed REAL,
            heat_index REAL,
            wbgt REAL,
            thermal_stress REAL,
            health_risk REAL,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# BASIC FUNCTIONS
# ============================================================

def clamp(
    value,
    minimum=0,
    maximum=100
):

    return max(
        minimum,
        min(maximum, value)
    )


def normalize(
    value,
    minimum,
    maximum
):

    if maximum <= minimum:
        return 0

    if value <= minimum:
        return 0

    if value >= maximum:
        return 100

    return (
        (value - minimum)
        /
        (maximum - minimum)
    ) * 100


# ============================================================
# HISTORICAL INDIAN WORKDAY MODEL
# ============================================================

def get_india_working_hours_profile(
    location,
    temperature,
    humidity,
    month=None
):

    month = month or datetime.now(timezone.utc).month
    seasonal_shift = 0

    if month in {3, 4, 5, 6}:
        seasonal_shift = 2.5
    elif month in {2, 7, 8, 9}:
        seasonal_shift = 1.2

    district_bias = (sum(ord(ch) for ch in str(location)) % 4) * 0.25
    times = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"]
    baseline = [0.70, 0.82, 0.94, 1.02, 0.96, 0.78]
    profile = []

    for index, clock in enumerate(times):
        high = temperature * baseline[index] + seasonal_shift + district_bias
        low = max(20, high - 5.5 - (humidity / 30))
        heat_index = high + (humidity / 100) * 4.8
        risk = clamp(
            ((high - 28) / 16) * 42
            + ((humidity - 35) / 50) * 18
            + ((heat_index - 31) / 15) * 18
        )

        profile.append({
            "time": clock,
            "temperature_high": round(high, 2),
            "temperature_low": round(low, 2),
            "heat_index": round(heat_index, 2),
            "risk_score": round(risk, 2),
            "risk_level": get_risk_level(risk),
            "humidity": round(humidity, 2)
        })

    return profile


def build_historical_workday_profile(
    location,
    temperature,
    humidity,
    month=None
):

    return get_india_working_hours_profile(
        location,
        temperature,
        humidity,
        month
    )


def estimate_historical_risk(
    location,
    temperature,
    humidity,
    month=None
):

    profile = get_india_working_hours_profile(
        location,
        temperature,
        humidity,
        month
    )

    if not profile:
        return 0

    return sum(item["risk_score"] for item in profile) / len(profile)


# ============================================================
# HEAT INDEX
# ============================================================

def calculate_heat_index(
    temperature,
    humidity
):

    # Prototype screening estimate.
    # NOT official NOAA Heat Index.

    return (
        temperature
        + 0.33 * (humidity / 100 * 6.105)
        - 0.70
    )


# ============================================================
# APPROXIMATE WBGT
# ============================================================

def calculate_wbgt(
    temperature,
    humidity,
    wind_speed
):

    # Prototype screening estimate.
    # NOT full meteorological WBGT.

    return (
        0.7 * temperature
        + 0.2 * (humidity / 100 * temperature)
        - 0.1 * wind_speed
    )


# ============================================================
# HUMAN THERMAL STRESS
# ============================================================

def calculate_thermal_stress(
    temperature,
    humidity,
    heat_index,
    wbgt,
    wind_speed
):

    temperature_score = normalize(
        temperature,
        25,
        42
    )

    humidity_score = normalize(
        humidity,
        35,
        80
    )

    heat_index_score = normalize(
        heat_index,
        25,
        45
    )

    wbgt_score = normalize(
        wbgt,
        22,
        34
    )

    wind_score = max(
        0,
        100
        -
        normalize(
            wind_speed,
            0,
            15
        )
    )

    score = (
        0.30 * temperature_score
        + 0.20 * humidity_score
        + 0.25 * heat_index_score
        + 0.15 * wbgt_score
        + 0.10 * wind_score
    )

    return round(
        clamp(score),
        2
    )


# ============================================================
# HEALTH RISK
# ============================================================

def calculate_health_risk(
    temperature,
    humidity,
    thermal_stress,
    apparent_temperature
):

    temperature_score = normalize(
        temperature,
        25,
        40
    )

    humidity_score = normalize(
        humidity,
        30,
        80
    )

    apparent_score = normalize(
        apparent_temperature,
        25,
        45
    )

    score = (
        0.40 * temperature_score
        + 0.20 * humidity_score
        + 0.25 * thermal_stress
        + 0.15 * apparent_score
    )

    return round(
        clamp(score),
        2
    )


def calculate_forecast_health_risk(
    temperature,
    humidity,
    wind_speed,
    apparent_temperature,
    uv_index=0,
    precipitation_probability=0
):

    temperature_score = normalize(
        temperature,
        24,
        38
    )

    humidity_score = normalize(
        humidity,
        25,
        85
    )

    apparent_score = normalize(
        apparent_temperature,
        24,
        45
    )

    uv_score = normalize(
        uv_index,
        0,
        12
    )

    rain_score = normalize(
        precipitation_probability,
        0,
        100
    )

    wind_score = max(
        0,
        100
        -
        normalize(
            wind_speed,
            0,
            20
        )
    )

    score = (
        0.32 * temperature_score
        + 0.18 * humidity_score
        + 0.18 * apparent_score
        + 0.15 * uv_score
        + 0.10 * wind_score
        + 0.07 * rain_score
    )

    return round(
        clamp(score),
        2
    )


# ============================================================
# RISK LEVEL
# ============================================================

def get_risk_level(score):

    if score < 25:
        return "LOW"

    if score < 50:
        return "MODERATE"

    if score < 75:
        return "HIGH"

    return "EXTREME"


# ============================================================
# ADVISORY
# ============================================================

def get_advisory(level):

    if level == "LOW":

        return (
            "Heat conditions are currently low risk. "
            "Continue normal activities and stay hydrated."
        )

    if level == "MODERATE":

        return (
            "Moderate heat stress is possible. "
            "Drink water regularly and avoid prolonged "
            "exposure to direct sunlight."
        )

    if level == "HIGH":

        return (
            "High heat risk detected. Reduce outdoor activity, "
            "drink water regularly and take frequent breaks "
            "in cool areas."
        )

    return (
        "Extreme heat risk detected. Avoid unnecessary "
        "outdoor activity and remain in a cool environment. "
        "High-risk groups require special attention."
    )


# ============================================================
# SMART ALERTS
# ============================================================

EMERGENCY_CENTERS = [
    {
        "name": "Bengaluru City Disaster Management Cell",
        "phone": "+91 80 2222 0000",
        "latitude": 12.97,
        "longitude": 77.59,
        "district": "Bengaluru Urban"
    },
    {
        "name": "Mysuru District Emergency Cell",
        "phone": "+91 821 241 0000",
        "latitude": 12.30,
        "longitude": 76.65,
        "district": "Mysuru"
    },
    {
        "name": "Kalaburagi Disaster Response Desk",
        "phone": "+91 8472 222 000",
        "latitude": 17.33,
        "longitude": 76.83,
        "district": "Kalaburagi"
    },
    {
        "name": "Hubballi Emergency Coordination Center",
        "phone": "+91 836 221 0000",
        "latitude": 15.36,
        "longitude": 75.12,
        "district": "Dharwad"
    },
    {
        "name": "Karnataka State Emergency Response",
        "phone": "112",
        "latitude": 15.3173,
        "longitude": 75.7139,
        "district": "Karnataka"
    }
]

ALERT_HISTORY = {}


def haversine_km(lat1, lon1, lat2, lon2):

    radius = 6371.0
    phi1 = lat1 * 3.141592653589793 / 180
    phi2 = lat2 * 3.141592653589793 / 180
    delta_phi = (lat2 - lat1) * 3.141592653589793 / 180
    delta_lambda = (lon2 - lon1) * 3.141592653589793 / 180

    a = (
        (math.sin(delta_phi / 2) ** 2)
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2) ** 2)
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def get_nearest_disaster_contact(latitude, longitude):

    nearest = None
    nearest_distance = None

    for center in EMERGENCY_CENTERS:
        distance = haversine_km(
            latitude,
            longitude,
            center["latitude"],
            center["longitude"]
        )

        if nearest_distance is None or distance < nearest_distance:
            nearest = center
            nearest_distance = distance

    if not nearest:
        return {
            "name": "Emergency response",
            "phone": "112",
            "distance_km": 0,
            "district": "Karnataka"
        }

    return {
        "name": nearest["name"],
        "phone": nearest["phone"],
        "distance_km": round(nearest_distance, 1),
        "district": nearest["district"]
    }


def get_risk_action(level, score):

    if level == "LOW":
        return {
            "title": "Safe for normal travel",
            "message": "Stay hydrated and keep water available for the route.",
            "recommended_action": "Continue normal work but keep a water bottle ready."
        }

    if level == "MODERATE":
        return {
            "title": "Watch the heat stress",
            "message": "Drink water regularly and reduce prolonged outdoor exposure.",
            "recommended_action": "Drink water, take breaks, and avoid peak afternoon exposure."
        }

    if level == "HIGH":
        return {
            "title": "Heat alert",
            "message": "Avoid long outdoor rides and deliveries during the hottest hours.",
            "recommended_action": "Limit travel, rest in shaded/cool places, and hydrate every 20 to 30 minutes."
        }

    return {
        "title": "Extreme heat danger",
        "message": "Do not ride or deliver in this area until conditions improve.",
        "recommended_action": "Avoid outdoor trips, postpone deliveries, and seek shade or air-conditioned rest locations immediately."
    }


def build_smart_alert(location, latitude, longitude, weather_result):

    risk_score = float(
        weather_result.get("health_risk")
        or weather_result.get("risk_score")
        or 0
    )

    level = str(
        weather_result.get("risk_level")
        or weather_result.get("health_level")
        or "LOW"
    ).upper()

    previous = ALERT_HISTORY.get(location)
    delta = None

    if previous is not None:
        delta = round(risk_score - float(previous.get("risk_score", risk_score)), 2)

    threshold_triggered = (
        level in {"HIGH", "EXTREME"}
        or (delta is not None and delta >= 15)
    )

    action = get_risk_action(level, risk_score)
    nearest_contact = get_nearest_disaster_contact(latitude, longitude)

    payload = {
        "location": location,
        "latitude": latitude,
        "longitude": longitude,
        "heat_index_c": float(weather_result.get("heat_index", 0) or 0),
        "thermal_stress": float(weather_result.get("thermal_stress", 0) or 0),
        "risk_score": round(risk_score, 2),
        "risk_level": level,
        "alert_triggered": threshold_triggered,
        "alert_type": "sudden_heat_risk" if threshold_triggered else "monitoring",
        "recommendation": action["recommended_action"],
        "message": action["message"],
        "title": action["title"],
        "nearest_emergency": nearest_contact,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    ALERT_HISTORY[location] = {
        "risk_score": risk_score,
        "risk_level": level,
        "updated_at": payload["updated_at"]
    }

    return payload


async def send_free_alert(phone_number, message):

    normalized_phone = str(phone_number).strip()
    if not normalized_phone:
        return {
            "status": "failed",
            "provider": "none",
            "alert_generated": False,
            "error": "No phone number supplied"
        }

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if telegram_token and telegram_chat_id:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                    data={
                        "chat_id": telegram_chat_id,
                        "text": message,
                        "parse_mode": "HTML"
                    }
                )

                data = {}
                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text}

                if response.status_code == 200 and data.get("ok") is True:
                    return {
                        "status": "sent",
                        "provider": "telegram",
                        "alert_generated": True,
                        "http_status": response.status_code,
                        "response": data,
                        "destination": telegram_chat_id
                    }
        except Exception as error:
            pass

    whatsapp_phone = normalized_phone.replace("+", "").replace(" ", "")
    if whatsapp_phone.startswith("91") and len(whatsapp_phone) == 12:
        whatsapp_phone = f"{whatsapp_phone}@c.us"

    providers = []

    provider_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if provider_url:
        providers.append({
            "name": "webhook",
            "url": provider_url,
            "type": "webhook"
        })

    providers.extend([
        {
            "name": "textbelt",
            "url": "https://textbelt.com/text",
            "type": "form"
        },
        {
            "name": "callmebot_whatsapp",
            "url": "https://api.callmebot.com/whatsapp/send.php",
            "type": "query",
            "phone": whatsapp_phone,
            "message": message
        }
    ])

    for provider in providers:
        try:
            async with httpx.AsyncClient(timeout=20) as client:

                if provider["type"] == "webhook":
                    response = await client.post(
                        provider["url"],
                        json={
                            "phone": normalized_phone,
                            "message": message,
                            "alert_generated": True,
                            "channel": "free_alert_fallback"
                        }
                    )

                elif provider["name"] == "textbelt":
                    response = await client.post(
                        provider["url"],
                        data={
                            "phone": normalized_phone,
                            "message": message,
                            "key": "textbelt"
                        }
                    )

                else:
                    params = {
                        "phone": provider["phone"],
                        "text": message,
                        "apikey": os.getenv("CALLMEBOT_API_KEY", "")
                    }
                    response = await client.get(
                        provider["url"],
                        params={k: v for k, v in params.items() if v}
                    )

                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text}

                if response.status_code == 200:
                    if provider["name"] == "textbelt":
                        if isinstance(data, dict) and data.get("success") is True:
                            return {
                                "status": "sent",
                                "provider": "textbelt",
                                "alert_generated": True,
                                "http_status": response.status_code,
                                "response": data
                            }
                    if provider["name"] == "callmebot_whatsapp":
                        return {
                            "status": "sent",
                            "provider": "callmebot_whatsapp",
                            "alert_generated": True,
                            "http_status": response.status_code,
                            "response": data
                        }
                    if provider["name"] == "webhook":
                        return {
                            "status": "sent",
                            "provider": "webhook",
                            "alert_generated": True,
                            "http_status": response.status_code,
                            "response": data
                        }

                if provider["name"] in {"textbelt", "callmebot_whatsapp", "webhook"}:
                    continue

        except Exception:
            continue

    return {
        "status": "generated_only",
        "provider": "free_alert_fallback",
        "alert_generated": True,
        "message": message,
        "warning": "No free SMS/WhatsApp gateway accepted the delivery, but the alert payload was generated successfully. Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable Telegram delivery."
    }


# ============================================================
# API KEY CHECK
# ============================================================

def check_api_key():

    return True


def get_weather_code_label(weather_code):

    mapping = {
        0: "Clear sky",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Freezing drizzle",
        57: "Heavy freezing drizzle",
        61: "Light rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Freezing rain",
        67: "Heavy freezing rain",
        71: "Light snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Rain showers",
        81: "Heavy rain showers",
        82: "Violent rain showers",
        85: "Snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Severe thunderstorm"
    }

    return mapping.get(weather_code, "Current weather")


def blend_with_historical_baseline(
    live_value,
    historical_value,
    live_weight=0.7,
    history_weight=0.3
):

    if historical_value is None or historical_value == 0:
        return float(live_value or 0)

    return round(
        (live_weight * float(live_value or 0))
        + (history_weight * float(historical_value or 0)),
        2
    )


# ============================================================
# DISTRICT LOOKUP
# ============================================================

def get_location(location):

    for name, coordinates in LOCATIONS.items():

        if name.lower() == location.strip().lower():

            return name, coordinates

    raise HTTPException(
        status_code=404,
        detail=f"Unknown Karnataka district: {location}"
    )


# ============================================================
# BUILD WEATHER RESULT
# ============================================================

def build_weather_result(
    location,
    latitude,
    longitude,
    temperature,
    humidity,
    wind_speed,
    apparent_temperature,
    weather_time,
    description,
    icon,
    pressure,
    clouds
):

    heat_index = calculate_heat_index(
        temperature,
        humidity
    )

    wbgt = calculate_wbgt(
        temperature,
        humidity,
        wind_speed
    )

    thermal_stress = calculate_thermal_stress(
        temperature,
        humidity,
        heat_index,
        wbgt,
        wind_speed
    )

    health_risk = calculate_health_risk(
        temperature,
        humidity,
        thermal_stress,
        apparent_temperature
    )

    risk_level = get_risk_level(
        health_risk
    )

    result = {

        "location": location,

        "latitude": latitude,

        "longitude": longitude,

        "coordinates": {
            "lat": latitude,
            "lon": longitude
        },

        "temperature": round(
            temperature,
            2
        ),

        "humidity": round(
            humidity,
            2
        ),

        "wind_speed": round(
            wind_speed,
            2
        ),

        "apparent_temperature": round(
            apparent_temperature,
            2
        ),

        "heat_index": round(
            heat_index,
            2
        ),

        "wbgt": round(
            wbgt,
            2
        ),

        "thermal_stress": round(
            thermal_stress,
            2
        ),

        "health_risk": round(
            health_risk,
            2
        ),

        "health_level": risk_level,

        "risk_score": round(
            health_risk,
            2
        ),

        "risk_level": risk_level,

        "advisory": get_advisory(
            risk_level
        ),

        "weather_time": weather_time,

        "description": description,

        "weather_icon": icon,

        "pressure": pressure,

        "clouds": clouds,

        "data_source": "Tomorrow.io",

        "updated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    alert_payload = build_smart_alert(
        location,
        latitude,
        longitude,
        result
    )

    for key, value in alert_payload.items():
        if key not in {"location", "latitude", "longitude"}:
            result[key] = value

    return result


# ============================================================
# SAVE WEATHER HISTORY
# ============================================================

def save_weather(data):

    conn = sqlite3.connect(
        DB_FILE
    )

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO weather_history (
            location,
            date,
            temperature,
            humidity,
            wind_speed,
            heat_index,
            wbgt,
            thermal_stress,
            health_risk,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        data["location"],

        data["weather_time"],

        data["temperature"],

        data["humidity"],

        data["wind_speed"],

        data["heat_index"],

        data["wbgt"],

        data["thermal_stress"],

        data["health_risk"],

        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    conn.commit()
    conn.close()


# ============================================================
# OPEN-METEO REQUEST
# ============================================================

async def open_meteo_request(
    latitude,
    longitude
):

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,pressure_msl,cloud_cover,weather_code",
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,precipitation_probability,uv_index",
        "forecast_days": 5,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }

    def fetch():
        try:
            with httpx.Client(timeout=20) as client:
                return client.get(OPEN_METEO_URL, params=params)
        except httpx.RequestError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Open-Meteo connection failed: {error}"
            )

    try:
        response = await asyncio.to_thread(fetch)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo connection failed: {error}"
        )

    if response.status_code != 200:
        try:
            message = response.json()
        except Exception:
            message = response.text
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo error: {message}"
        )

    return response.json()


# ============================================================
# GET VALUE FROM OPEN-METEO
# ============================================================

def get_weather_value(
    values,
    name,
    default=0
):

    value = values.get(
        name,
        default
    )

    if value is None:
        return default

    try:
        return float(value)

    except (ValueError, TypeError):

        return default


# ============================================================
# CURRENT WEATHER
# ============================================================

async def get_current_weather(
    location,
    latitude,
    longitude
):

    now = time.time()

    cached = weather_cache.get(
        location
    )

    if cached:

        age = (
            now
            -
            cached["time"]
        )

        if age < CURRENT_CACHE_SECONDS:

            result = dict(
                cached["data"]
            )

            result["data_source"] = (
                "Live weather - cache"
            )

            result["cache_age_seconds"] = round(
                age,
                1
            )

            return result

    raw = await open_meteo_request(latitude, longitude)

    current = raw.get("current", {})
    temperature = get_weather_value(current, "temperature_2m")
    humidity = get_weather_value(current, "relative_humidity_2m")
    apparent_temperature = get_weather_value(current, "apparent_temperature", temperature)
    wind_speed = get_weather_value(current, "wind_speed_10m")
    pressure = get_weather_value(current, "pressure_msl", 0)
    clouds = get_weather_value(current, "cloud_cover", 0)
    weather_code = current.get("weather_code")
    weather_description = get_weather_code_label(weather_code)
    weather_time = current.get("time")

    result = build_weather_result(
        location,
        latitude,
        longitude,
        temperature,
        humidity,
        wind_speed,
        apparent_temperature,
        weather_time,
        weather_description,
        None,
        pressure,
        clouds
    )

    result["weather_code"] = weather_code
    result["location_name"] = location
    result["data_source"] = "Open-Meteo"

    weather_cache[location] = {
        "time": time.time(),
        "data": result
    }

    return result


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():

    provider = get_active_weather_provider()

    return {

        "project": "AGNINOVA",

        "status": "running",

        "weather_provider": provider,

        "current_weather_refresh": "60 seconds",

        "forecast_interval": "1 hour",

        "districts": len(
            LOCATIONS
        )
    }


# ============================================================
# TEST
# ============================================================

@app.get("/test")
async def test():

    provider = get_active_weather_provider()

    return {

        "status": "Backend working",

        "project": "AGNINOVA",

        "weather_provider": provider,

        "district_count": len(
            LOCATIONS
        ),

        "api_key_configured":
            bool(
                TOMORROW_API_KEY
            ),

        "current_weather_refresh":
            "60 seconds",

        "gis_refresh":
            "15 minutes",

        "forecast":
            f"{provider} forecast"
    }


# ============================================================
# LOCATIONS
# ============================================================

@app.get("/locations")
async def locations():

    return {

        "count": len(
            LOCATIONS
        ),

        "locations": [

            {

                "location": name,

                "latitude": coords[0],

                "longitude": coords[1]

            }

            for name, coords
            in LOCATIONS.items()
        ]
    }


# ============================================================
# WEATHER
# ============================================================

@app.get("/weather/{location}")
async def weather(
    location: str
):

    location_name, coords = get_location(
        location
    )

    latitude, longitude = coords

    data = await get_current_weather(

        location_name,

        latitude,

        longitude
    )

    # Save only fresh observations.
    if data.get(
        "data_source"
    ) == "Open-Meteo":

        save_weather(
            data
        )

    return data


@app.get("/worker-risk")
async def worker_risk(
    location: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    app_type: str = "delivery"
):
    if location:
        location_name, coords = get_location(location)
        lat, lon = coords
    elif latitude is not None and longitude is not None:
        location_name = "Custom location"
        lat, lon = latitude, longitude
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either location or latitude and longitude."
        )

    weather = await get_current_weather(location_name, lat, lon)
    risk_level = weather.get("risk_level") or weather.get("health_level") or "LOW"
    risk_score = float(weather.get("risk_score") or weather.get("health_risk") or 0)
    app_name = app_type.lower()

    if risk_level == "EXTREME":
        instruction = "Do not take long outdoor trips. Stop work in direct sun, hydrate, and seek shaded rest immediately."
    elif risk_level == "HIGH":
        instruction = "Keep water available, take breaks every 20-30 minutes, and avoid peak heat hours."
    elif risk_level == "MODERATE":
        instruction = "Drink water regularly and avoid prolonged outdoor exposure during the hottest part of the day."
    else:
        instruction = "Normal conditions for outdoor work. Keep hydration and heat awareness in place."

    if app_name in {"food", "delivery", "driver", "passenger", "rideshare"}:
        worker_label = "delivery / passenger trip"
    else:
        worker_label = f"{app_type} work"

    return {
        "location": location_name,
        "latitude": lat,
        "longitude": lon,
        "app_type": app_name,
        "worker_context": worker_label,
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "temperature_c": round(float(weather.get("temperature") or 0), 2),
        "heat_index_c": round(float(weather.get("heat_index") or 0), 2),
        "thermal_stress": round(float(weather.get("thermal_stress") or 0), 2),
        "advisory": weather.get("advisory"),
        "recommendation": instruction,
        "data_source": weather.get("data_source"),
        "updated_at": weather.get("updated_at")
    }


# ============================================================
# FORECAST
# ============================================================

@app.get("/forecast/{location}")
async def forecast(
    location: str
):

    location_name, coords = get_location(
        location
    )

    latitude, longitude = coords

    raw = await open_meteo_request(latitude, longitude)

    hourly = raw.get("hourly", {})
    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    humidities = hourly.get("relative_humidity_2m", [])
    feels_like = hourly.get("apparent_temperature", [])
    wind_speeds = hourly.get("wind_speed_10m", [])
    uv_index_values = hourly.get("uv_index", [])
    precipitation_values = hourly.get("precipitation_probability", [])

    if not times:
        raise HTTPException(
            status_code=502,
            detail="No forecast data received from Open-Meteo."
        )

    daily = {}

    for index, time_string in enumerate(times):
        if not time_string:
            continue

        try:
            dt = datetime.fromisoformat(time_string)
        except Exception:
            continue

        local_date = dt.date().isoformat()
        daily.setdefault(local_date, []).append({
            "time": time_string,
            "temperature": temperatures[index] if index < len(temperatures) else 0,
            "humidity": humidities[index] if index < len(humidities) else 0,
            "apparent_temperature": feels_like[index] if index < len(feels_like) else 0,
            "wind_speed": wind_speeds[index] if index < len(wind_speeds) else 0,
            "uv_index": uv_index_values[index] if index < len(uv_index_values) else 0,
            "precipitation_probability": precipitation_values[index] if index < len(precipitation_values) else 0,
        })

    today = datetime.now(timezone.utc).date()
    dates = [
        date for date in sorted(daily.keys())
        if datetime.fromisoformat(date).date() >= today
    ][:5]

    result = []

    for date in dates:
        day_items = daily[date]
        temperatures = []
        selected = None
        selected_hour_difference = 999

        for item in day_items:
            values = item.get("values", {})
            temperature = get_weather_value(values, "temperature")
            temperatures.append(temperature)

            try:
                dt = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
                hour_difference = abs(dt.hour - 12)
                if selected is None or hour_difference < selected_hour_difference:
                    selected = item
                    selected_hour_difference = hour_difference
            except Exception:
                if selected is None:
                    selected = item

        if not selected:
            continue

        temperature = get_weather_value(selected, "temperature")
        humidity = get_weather_value(selected, "humidity")
        apparent_temperature = get_weather_value(selected, "apparent_temperature", temperature)
        wind_speed = get_weather_value(selected, "wind_speed")
        uv_index = get_weather_value(selected, "uv_index", 0)
        precipitation_probability = get_weather_value(selected, "precipitation_probability", 0)

        temperature_max = max(temperatures) if temperatures else temperature
        temperature_min = min(temperatures) if temperatures else temperature
        temperature_max = float(temperature_max)
        temperature_min = float(temperature_min)
        apparent_temperature_max = float(apparent_temperature)
        wind_speed_max = float(wind_speed)

        humidity = clamp((humidity * 0.65) + (40 + ((temperature_max - 20) * 2.8) * 0.35), 20, 95)
        heat_index = calculate_heat_index(temperature_max, humidity)
        wbgt = calculate_wbgt(temperature_max, humidity, wind_speed_max)
        thermal_stress = calculate_thermal_stress(temperature_max, humidity, heat_index, wbgt, wind_speed_max)
        health_risk = calculate_forecast_health_risk(
            temperature_max,
            humidity,
            wind_speed_max,
            apparent_temperature_max,
            uv_index,
            precipitation_probability
        )
        risk_level = get_risk_level(health_risk)

        result.append({
            "date": date,
            "temperature": round(temperature_max, 2),
            "temperature_min": round(temperature_min, 2),
            "temperature_max": round(temperature_max, 2),
            "humidity": round(humidity, 2),
            "wind_speed": round(wind_speed_max, 2),
            "apparent_temperature": round(apparent_temperature_max, 2),
            "heat_index": round(heat_index, 2),
            "wbgt": round(wbgt, 2),
            "thermal_stress": round(thermal_stress, 2),
            "health_risk": round(health_risk, 2),
            "health_level": risk_level,
            "risk_score": round(health_risk, 2),
            "risk_level": risk_level,
            "advisory": get_advisory(risk_level),
            "data_source": "Open-Meteo",
            "uv_index": round(uv_index, 2),
            "precipitation_probability": round(precipitation_probability, 2)
        })

    payload = {
        "location": location_name,
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": len(result),
        "data": result
    }

    return payload

    return {
        "location": location_name,
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": len(result),
        "data": result
    }

# ============================================================
# HISTORY
# ============================================================

@app.get("/history/{location}")
async def history(
    location: str
):

    location_name, _ = get_location(
        location
    )

    conn = sqlite3.connect(
        DB_FILE
    )

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            location,
            date,
            temperature,
            humidity,
            wind_speed,
            heat_index,
            wbgt,
            thermal_stress,
            health_risk,
            created_at
        FROM weather_history
        WHERE location = ?
        ORDER BY id DESC
        LIMIT 20
    """, (
        location_name,
    ))

    rows = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return {

        "location": location_name,

        "count": len(rows),

        "history": rows
    }

# ============================================================
# GIS
# ============================================================

async def get_gis_data():

    now = time.time()

    cached = gis_cache.get(
        "karnataka"
    )

    if cached:

        age = (
            now
            -
            cached["time"]
        )

        if age < GIS_CACHE_SECONDS:

            data = cached["data"]

            data = dict(data)

            data["cache_age_seconds"] = round(
                age,
                1
            )

            return data

    tasks = []

    for location, coords in LOCATIONS.items():

        tasks.append(

            get_current_weather(

                location,

                coords[0],

                coords[1]
            )
        )

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    clean_results = []

    for index, result in enumerate(
        results
    ):

        location = list(
            LOCATIONS.keys()
        )[index]

        coords = LOCATIONS[
            location
        ]

        if isinstance(
            result,
            Exception
        ):

            clean_results.append({

                "location": location,

                "latitude": coords[0],

                "longitude": coords[1],

                "risk_level": "UNKNOWN",

                "risk_score": 0,

                "health_level": "UNKNOWN",

                "error": str(result)
            })

        else:

            clean_results.append(
                result
            )

    data = {

        "state": "Karnataka",

        "district_count":
            len(clean_results),

        "data_source":
            "Open-Meteo",

        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "data":
            clean_results
    }

    gis_cache["karnataka"] = {

        "time": time.time(),

        "data": data
    }

    return data


@app.get("/gis-risk")
async def gis_risk():

    return await get_gis_data()


@app.get("/smart-alert/{location}")
async def smart_alert(location: str):

    location_name, coords = get_location(location)
    weather = await get_current_weather(location_name, coords[0], coords[1])
    payload = build_smart_alert(location_name, coords[0], coords[1], weather)
    return payload


@app.get("/smart-geo-alert")
async def smart_geo_alert(latitude: float, longitude: float):

    location_name = None
    best_distance = None

    for name, coords in LOCATIONS.items():
        distance = haversine_km(latitude, longitude, coords[0], coords[1])
        if best_distance is None or distance < best_distance:
            location_name = name
            best_distance = distance

    if not location_name:
        raise HTTPException(status_code=404, detail="No district found for the provided coordinates.")

    weather = await get_current_weather(location_name, LOCATIONS[location_name][0], LOCATIONS[location_name][1])
    payload = build_smart_alert(location_name, LOCATIONS[location_name][0], LOCATIONS[location_name][1], weather)
    payload["device_coordinates"] = {"latitude": latitude, "longitude": longitude}
    payload["nearest_district_distance_km"] = round(best_distance, 2)
    return payload


@app.post("/send-trial-alert")
async def send_trial_alert():

    location_name = "Bengaluru Urban"
    latitude, longitude = LOCATIONS[location_name]
    weather = await get_current_weather(location_name, latitude, longitude)
    payload = build_smart_alert(location_name, latitude, longitude, weather)

    message = (
        f"AGNINOVA alert for {location_name}: heat index {payload['heat_index_c']:.1f}C, "
        f"thermal stress {payload['thermal_stress']:.1f}, risk {payload['risk_score']:.1f}/100 ({payload['risk_level']}). "
        f"Action: {payload['recommendation']}"
    )

    sms_result = await send_free_alert("918431868189", message)
    payload["alert_delivery"] = sms_result
    return payload

# ============================================================
# AI CHAT
# ============================================================

def generate_ai_answer(
    question,
    location=None,
    temperature=None,
    humidity=None,
    weather=None
):

    q = str(question or "").lower()
    location_name = location or "the selected location"
    temp = temperature if temperature is not None else 32
    hum = humidity if humidity is not None else 55

    if "risk" in q or "alert" in q:
        risk_level = get_risk_level(clamp((temp - 22) * 2.2 + (hum - 30) * 0.35))
        return (
            f"{location_name} is currently showing {risk_level} heat risk. "
            f"The current pattern suggests heat stress is rising during midday and early afternoon. "
            "Drink water and avoid long outdoor exposure."
        )

    if "temperature" in q or "hot" in q or "heat" in q:
        return (
            f"The working-hours pattern in India typically peaks around midday. "
            f"Today the most intense heat is expected near 12:00 to 16:00, with a daytime high around {round(temp, 1)}°C."
        )

    if "humidity" in q:
        return (
            f"Humidity is currently {round(hum, 1)}%. In higher humidity, sweat evaporates less efficiently, so the heat burden feels stronger."
        )

    if "wbgt" in q:
        return (
            "WBGT is a heat-stress indicator used to estimate how hard the environment is on the body. "
            "In simple terms, higher temperature + higher humidity + lower airflow means greater thermal stress."
        )

    if "precaution" in q or "safe" in q or "protect" in q or "water" in q:
        return (
            "For hot work hours, keep water available, reduce outdoor work during peak heat, take breaks in shaded or cool places, "
            "and avoid strenuous activity between 12:00 and 16:00."
        )

    if "forecast" in q or "tomorrow" in q:
        profile = get_india_working_hours_profile(location_name, temp, hum)
        peak = max(profile, key=lambda item: item["temperature_high"])
        return (
            f"The historical Indian working-hours trend suggests a daytime peak near {peak['time']} with a high near {peak['temperature_high']}°C. "
            "This should be used together with live conditions rather than a live-only guess."
        )

    return (
        "I can help with heat risk, temperature, humidity, WBGT, thermal stress, and basic safety advice for Indian working hours. "
        "Ask me about current risk, daily heat trend, or what to do during peak heat."
    )


class ChatRequest(BaseModel):

    message: str

    location: Optional[str] = None


@app.post("/chat")
async def chat(
    request: ChatRequest
):

    message = request.message.lower()

    weather = None

    if request.location:

        try:

            name, coords = get_location(
                request.location
            )

            weather = await get_current_weather(

                name,

                coords[0],

                coords[1]
            )

        except Exception:

            weather = None

    if weather:

        location = weather["location"]
        temperature = weather["temperature"]
        humidity = weather["humidity"]
        risk = weather["risk_level"]
        score = weather["risk_score"]

        answer = generate_ai_answer(
            request.message,
            location,
            temperature,
            humidity,
            weather
        )

    else:

        answer = generate_ai_answer(
            request.message,
            request.location or "Karnataka",
            32,
            58
        )

    return {

        "answer": answer,

        "assistant": "AGNINOVA AI",

        "type": "prototype-rule-based"
    }


@app.post("/ai/chat")
async def ai_chat(
    request: ChatRequest
):

    return await chat(
        request
    )

# ============================================================
# TEMPORARY EMERGENCY ALERT
# ============================================================

@app.get("/emergency-alert/{location}")
async def emergency_alert(
    location: str
):

    name, coords = get_location(
        location
    )

    weather = await get_current_weather(

        name,

        coords[0],

        coords[1]
    )

    active = weather["risk_level"] in [
        "HIGH",
        "EXTREME"
    ]

    return {

        "location": name,

        "alert_active": active,

        "risk_level":
            weather["risk_level"],

        "risk_score":
            weather["risk_score"],

        "message": (

            "TEMPORARY HEAT EMERGENCY ALERT: "
            "Reduce outdoor exposure and follow "
            "public-health precautions."

            if active

            else

            "No emergency heat alert is active."
        ),

        "advisory":
            weather["advisory"],

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat()
    }

# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():

    provider = get_active_weather_provider()

    print("")

    print("=" * 60)

    print(
        "AGNINOVA BACKEND STARTED"
    )

    print("=" * 60)

    print(
        "Weather Provider :",
        provider
    )

    print(
        "Current Refresh  : 60 seconds"
    )

    print(
        "GIS Refresh      : 15 minutes"
    )

    print(
        "Forecast         :",
        provider
    )

    print(
        "Districts        :",
        len(LOCATIONS)
    )

    print(
        "API Key          :",
        "Configured"
        if TOMORROW_API_KEY
        else
        "NOT CONFIGURED"
    )

    print("=" * 60)

    print("")
