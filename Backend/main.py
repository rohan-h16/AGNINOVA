import os
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
# Tomorrow.io Weather Intelligence
# ============================================================

app = FastAPI(
    title="AGNINOVA",
    description="Extreme Heatwave Early Warning & Human Thermal Stress Platform",
    version="4.0"
)


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
# TOMORROW.IO CONFIG
# ============================================================

TOMORROW_API_KEY = os.getenv(
    "TOMORROW_API_KEY",
    ""
).strip()

TOMORROW_URL = (
    "https://api.tomorrow.io/v4/weather/realtime"
)

TOMORROW_FORECAST_URL = (
    "https://api.tomorrow.io/v4/weather/forecast"
)

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

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
        30,
        45
    )

    humidity_score = normalize(
        humidity,
        50,
        90
    )

    heat_index_score = normalize(
        heat_index,
        30,
        50
    )

    wbgt_score = normalize(
        wbgt,
        25,
        35
    )

    wind_score = (
        100
        -
        normalize(
            wind_speed,
            0,
            10
        )
    )

    score = (
        0.25 * temperature_score
        + 0.20 * humidity_score
        + 0.25 * heat_index_score
        + 0.20 * wbgt_score
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
        35,
        45
    )

    humidity_score = normalize(
        humidity,
        50,
        90
    )

    apparent_score = normalize(
        apparent_temperature,
        35,
        50
    )

    score = (
        0.35 * temperature_score
        + 0.25 * humidity_score
        + 0.25 * thermal_stress
        + 0.15 * apparent_score
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
# TOMORROW.IO API KEY CHECK
# ============================================================

def check_api_key():

    if not TOMORROW_API_KEY:

        raise HTTPException(
            status_code=500,
            detail=(
                "TOMORROW_API_KEY is not configured. "
                "Run: export TOMORROW_API_KEY=\"YOUR_KEY\""
            )
        )


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


async def open_meteo_request(latitude, longitude):

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,pressure_msl,cloud_cover,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo connection failed: {error}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo error: HTTP {response.status_code}"
        )

    return response.json()


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

    return {

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
# TOMORROW.IO REQUEST
# ============================================================

async def tomorrow_request(
    url,
    latitude,
    longitude
):

    check_api_key()

    params = {

        "location": f"{latitude},{longitude}",

        "apikey": TOMORROW_API_KEY
    }

    try:

        async with httpx.AsyncClient(
            timeout=15
        ) as client:

            response = await client.get(
                url,
                params=params
            )

    except httpx.RequestError as error:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Tomorrow.io connection failed: {error}"
            )
        )

    if response.status_code in [401, 403]:

        raise HTTPException(
            status_code=502,
            detail=(
                "Invalid or unauthorized Tomorrow.io API key."
            )
        )

    if response.status_code == 429:

        raise HTTPException(
            status_code=502,
            detail=(
                "Tomorrow.io rate limit reached. "
                "Please wait before making another request."
            )
        )

    if response.status_code != 200:

        try:

            error_data = response.json()

            message = str(
                error_data
            )

        except Exception:

            message = response.text

        raise HTTPException(
            status_code=502,
            detail=(
                f"Tomorrow.io error: {message}"
            )
        )

    return response.json()


# ============================================================
# GET VALUE FROM TOMORROW.IO
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

    if TOMORROW_API_KEY:
        raw = await tomorrow_request(
            TOMORROW_URL,
            latitude,
            longitude
        )

        data = raw.get(
            "data",
            {}
        )

        values = data.get(
            "values",
            {}
        )

        temperature = get_weather_value(
            values,
            "temperature"
        )

        humidity = get_weather_value(
            values,
            "humidity"
        )

        apparent_temperature = get_weather_value(
            values,
            "temperatureApparent",
            temperature
        )

        wind_speed = get_weather_value(
            values,
            "windSpeed"
        )

        wind_speed = wind_speed * 3.6

        pressure = get_weather_value(
            values,
            "pressureSurfaceLevel",
            0
        )

        clouds = get_weather_value(
            values,
            "cloudCover",
            0
        )

        weather_code = values.get(
            "weatherCode"
        )

        weather_description = (
            f"Weather code {weather_code}"
            if weather_code is not None
            else "Current weather"
        )

        weather_time = data.get(
            "time"
        )

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
        result["data_source"] = "Tomorrow.io"
    else:
        raw = await open_meteo_request(latitude, longitude)

        current = raw.get("current", {})

        temperature = get_weather_value(current, "temperature_2m")
        humidity = get_weather_value(current, "relative_humidity_2m")
        apparent_temperature = get_weather_value(current, "apparent_temperature", temperature)
        wind_speed = get_weather_value(current, "wind_speed_10m") * 3.6
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

    return {

        "project": "AGNINOVA",

        "status": "running",

        "weather_provider": "Tomorrow.io",

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

    return {

        "status": "Backend working",

        "project": "AGNINOVA",

        "weather_provider": "Tomorrow.io",

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
            "Tomorrow.io forecast"
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
    ) == "Tomorrow.io":

        save_weather(
            data
        )

    return data


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

    if TOMORROW_API_KEY:
        raw = await tomorrow_request(
            TOMORROW_FORECAST_URL,
            latitude,
            longitude
        )

        timelines = raw.get(
            "timelines",
            {}
        )

        hourly = timelines.get(
            "hourly",
            []
        )

        if not hourly:
            raise HTTPException(
                status_code=502,
                detail="No forecast data received."
            )

        daily = {}

        for item in hourly:
            time_string = item.get("time")
            if not time_string:
                continue

            try:
                dt = datetime.fromisoformat(
                    time_string.replace("Z", "+00:00")
                )
            except Exception:
                continue

            local_date = dt.date().isoformat()
            daily.setdefault(local_date, []).append(item)

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

            values = selected.get("values", {})
            temperature = get_weather_value(values, "temperature")
            humidity = get_weather_value(values, "humidity")
            apparent_temperature = get_weather_value(values, "temperatureApparent", temperature)
            wind_speed = get_weather_value(values, "windSpeed") * 3.6
            heat_index = calculate_heat_index(temperature, humidity)
            wbgt = calculate_wbgt(temperature, humidity, wind_speed)
            thermal_stress = calculate_thermal_stress(temperature, humidity, heat_index, wbgt, wind_speed)
            health_risk = calculate_health_risk(temperature, humidity, thermal_stress, apparent_temperature)
            risk_level = get_risk_level(health_risk)

            result.append({
                "date": date,
                "temperature": round(temperature, 2),
                "temperature_min": round(min(temperatures), 2),
                "temperature_max": round(max(temperatures), 2),
                "humidity": round(humidity, 2),
                "wind_speed": round(wind_speed, 2),
                "apparent_temperature": round(apparent_temperature, 2),
                "heat_index": round(heat_index, 2),
                "wbgt": round(wbgt, 2),
                "thermal_stress": round(thermal_stress, 2),
                "health_risk": round(health_risk, 2),
                "health_level": risk_level,
                "risk_score": round(health_risk, 2),
                "risk_level": risk_level,
                "advisory": get_advisory(risk_level),
                "data_source": "Tomorrow.io"
            })

        payload = {
            "location": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": len(result),
            "data": result
        }

        return payload

    raw = await open_meteo_request(latitude, longitude)
    daily = raw.get("daily", {})
    dates = daily.get("time", [])[:5]

    if not dates:
        raise HTTPException(
            status_code=502,
            detail="No forecast data received from Open-Meteo."
        )

    result = []
    for index, date in enumerate(dates):
        temperature_max = get_weather_value(daily, "temperature_2m_max")
        temperature_min = get_weather_value(daily, "temperature_2m_min")
        apparent_temperature_max = get_weather_value(daily, "apparent_temperature_max")
        wind_speed_max = get_weather_value(daily, "wind_speed_10m_max")

        if isinstance(temperature_max, list):
            temperature_max = temperature_max[index]
        if isinstance(temperature_min, list):
            temperature_min = temperature_min[index]
        if isinstance(apparent_temperature_max, list):
            apparent_temperature_max = apparent_temperature_max[index]
        if isinstance(wind_speed_max, list):
            wind_speed_max = wind_speed_max[index]

        humidity = 50 + (index * 4)
        heat_index = calculate_heat_index(temperature_max, humidity)
        wbgt = calculate_wbgt(temperature_max, humidity, wind_speed_max * 3.6)
        thermal_stress = calculate_thermal_stress(temperature_max, humidity, heat_index, wbgt, wind_speed_max * 3.6)
        health_risk = calculate_health_risk(temperature_max, humidity, thermal_stress, apparent_temperature_max)
        risk_level = get_risk_level(health_risk)

        result.append({
            "date": date,
            "temperature": round(temperature_max, 2),
            "temperature_min": round(temperature_min, 2),
            "temperature_max": round(temperature_max, 2),
            "humidity": round(humidity, 2),
            "wind_speed": round(wind_speed_max * 3.6, 2),
            "apparent_temperature": round(apparent_temperature_max, 2),
            "heat_index": round(heat_index, 2),
            "wbgt": round(wbgt, 2),
            "thermal_stress": round(thermal_stress, 2),
            "health_risk": round(health_risk, 2),
            "health_level": risk_level,
            "risk_score": round(health_risk, 2),
            "risk_level": risk_level,
            "advisory": get_advisory(risk_level),
            "data_source": "Open-Meteo"
        })

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
            "Tomorrow.io",

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

# ============================================================
# AI CHAT
# ============================================================

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

        if "risk" in message:

            answer = (

                f"{location} currently has "
                f"{risk} heat-health risk. "
                f"The risk score is "
                f"{score}/100."
            )

        elif (
            "temperature" in message
            or
            "hot" in message
        ):

            answer = (

                f"{location} is currently "
                f"{temperature}°C with "
                f"{humidity}% humidity. "
                f"Current risk is {risk}."
            )

        elif (
            "water" in message
            or
            "hydration" in message
        ):

            answer = (

                "Drink water regularly, "
                "avoid prolonged direct sunlight "
                "and take breaks in cool areas."
            )

        elif "wbgt" in message:

            answer = (

                f"The approximate WBGT screening "
                f"estimate for {location} is "
                f"{weather['wbgt']}°C."
            )

        elif (
            "humidity" in message
        ):

            answer = (

                f"The current humidity in "
                f"{location} is {humidity}%."
            )

        else:

            answer = weather["advisory"]

    else:

        answer = (

            "I can help with heat risk, "
            "temperature, humidity, WBGT, "
            "thermal stress and safety advice."
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

    print("")

    print("=" * 60)

    print(
        "AGNINOVA BACKEND STARTED"
    )

    print("=" * 60)

    print(
        "Weather Provider : Tomorrow.io"
    )

    print(
        "Current Refresh  : 60 seconds"
    )

    print(
        "GIS Refresh      : 15 minutes"
    )

    print(
        "Forecast         : Tomorrow.io"
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
