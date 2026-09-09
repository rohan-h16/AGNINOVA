/* ============================================================
   AGNINOVA FRONTEND
   HTML + CSS + JavaScript
   Backend: FastAPI
   ============================================================ */


/* BACKEND */

const BACKEND_URL = (
    window.__AGNINOVA_BACKEND_URL__ ||
    "https://agninova.onrender.com"
).replace(/\/$/, "");

const BACKEND_FALLBACK_URLS = [
    BACKEND_URL,
    "http://127.0.0.1:8000",
    "https://agninova.onrender.com"
].filter((value, index, array) => value && array.indexOf(value) === index);


/* GLOBAL */

let currentWeather = null;
let map = null;
let forecastChart = null;
let districtMarkers = [];
let districtPolygons = [];
let autoRefreshTimer = null;
let districtBoundaryGeoJson = null;

let selectedDistrict = "Bengaluru Urban";
const AUTO_REFRESH_MS = 60000;


/* ============================================================
   INITIALIZATION
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {

    initializeDistricts();

    initializeMap();

    initializeAutoRefresh();

    checkBackend();

    loadDashboard();

    document
        .getElementById("districtSelect")
        .addEventListener("change", function () {

            selectedDistrict = this.value;

            loadDashboard();

        });

});


/* ============================================================
   NAVIGATION
   ============================================================ */

function showSection(sectionId) {

    document.querySelectorAll(".section")
        .forEach(section => {

            section.classList.remove("active");

        });


    const section =
        document.getElementById(sectionId);

    if (section) {
        section.classList.add("active");
    }


    document.querySelectorAll(".nav-item")
        .forEach(item => {

            item.classList.remove("active");

        });


    const navItems =
        document.querySelectorAll(".nav-item");

    navItems.forEach(item => {

        const onclick =
            item.getAttribute("onclick") || "";

        if (onclick.includes(sectionId)) {
            item.classList.add("active");
        }

    });


    if (sectionId === "mapSection") {

        setTimeout(() => {

            if (map) {
                map.invalidateSize();
            }

            loadGIS();

        }, 200);

    }


    if (sectionId === "forecastSection") {
        loadForecast();
    }

}


/* ============================================================
   DISTRICTS
   ============================================================ */

const districts = [

    "Bagalkot",
    "Ballari",
    "Belagavi",
    "Bengaluru Urban",
    "Bengaluru Rural",
    "Bidar",
    "Chamarajanagar",
    "Chikkaballapur",
    "Chikkamagaluru",
    "Chitradurga",
    "Dakshina Kannada",
    "Davanagere",
    "Dharwad",
    "Gadag",
    "Hassan",
    "Haveri",
    "Kalaburagi",
    "Kodagu",
    "Kolar",
    "Koppal",
    "Mandya",
    "Mysuru",
    "Raichur",
    "Ramanagara",
    "Shivamogga",
    "Tumakuru",
    "Udupi",
    "Uttara Kannada",
    "Vijayapura",
    "Yadgir",
    "Vijayanagara"

];


function initializeDistricts() {

    const select =
        document.getElementById("districtSelect");

    select.innerHTML = "";

    districts.forEach(district => {

        const option =
            document.createElement("option");

        option.value = district;

        option.textContent = district;

        if (district === selectedDistrict) {
            option.selected = true;
        }

        select.appendChild(option);

    });

}


/* ============================================================
   BACKEND STATUS
   ============================================================ */

async function checkBackend() {

    const dot =
        document.getElementById("statusDot");

    const text =
        document.getElementById("connectionText");

    const apiSignal = document.getElementById("apiSignalDot");
    const apiLabel = document.getElementById("apiSourceLabel");

    try {

        const response =
            await fetch(`${BACKEND_URL}/test`);

        if (!response.ok) {
            throw new Error("Backend error");
        }

        const data = await response.json();
        const source = data.weather_provider || "Live weather";

        dot.classList.add("online");
        if (apiSignal) apiSignal.classList.add("online");

        text.textContent =
            "Backend Online";

        if (apiLabel) {
            apiLabel.textContent = `API: ${source}`;
        }

        updateRefreshStatus("Auto-refresh: every 60 seconds");

    }

    catch (error) {

        dot.classList.remove("online");
        if (apiSignal) apiSignal.classList.remove("online");

        text.textContent =
            "Backend Offline";

        if (apiLabel) {
            apiLabel.textContent = "API: fallback demo";
        }

        updateRefreshStatus("Auto-refresh: every 60 seconds (fallback mode)");

        console.warn(
            "FastAPI backend unavailable:",
            error
        );

    }

}


/* ============================================================
   DASHBOARD
   ============================================================ */

async function loadDashboard() {

    await checkBackend();

    await loadWeather();

    await loadHotspotList();

}


function initializeAutoRefresh() {

    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
    }

    autoRefreshTimer = setInterval(() => {
        loadDashboard();
    }, AUTO_REFRESH_MS);

    updateRefreshStatus();

}


function updateRefreshStatus(text) {

    const refreshEl = document.getElementById("refreshStatus");

    if (!refreshEl) {
        return;
    }

    refreshEl.textContent = text || "Auto-refresh: every 60 seconds";

}


/* ============================================================
   WEATHER
   ============================================================ */

async function loadWeather() {

    setLoadingState();


    try {

        const encoded =
            encodeURIComponent(selectedDistrict);


        const response =
            await fetch(
                `${BACKEND_URL}/weather/${encoded}`
            );


        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        currentWeather = data;


        renderWeather(data);

    }

    catch (error) {

        console.warn(
            "Weather backend unavailable; using demo heat-risk data.",
            error
        );

        const demoWeather = generateDemoWeather(selectedDistrict);
        currentWeather = demoWeather;
        renderWeather(demoWeather);

    }

}


function normalizeDemo(value, minimum, maximum) {
    if (maximum <= minimum) return 0;
    if (value <= minimum) return 0;
    if (value >= maximum) return 100;
    return ((value - minimum) / (maximum - minimum)) * 100;
}

function clampDemo(value, minimum = 0, maximum = 100) {
    return Math.min(maximum, Math.max(minimum, value));
}

function generateDemoWeather(location) {

    const seed = location
        .split("")
        .reduce((total, char) => total + char.charCodeAt(0), 0);

    const temperature = 28 + (seed % 12);
    const humidity = 40 + (seed % 35);
    const windSpeed = 3 + (seed % 18);
    const apparentTemperature = temperature + 2 + (seed % 5);
    const heatIndex = temperature + 3 + (humidity / 100 * 8);
    const wbgt = (0.7 * temperature) + (0.2 * humidity * 0.01 * temperature) - (0.1 * windSpeed);

    const temperatureScore = normalizeDemo(temperature, 25, 42);
    const humidityScore = normalizeDemo(humidity, 35, 80);
    const heatIndexScore = normalizeDemo(heatIndex, 25, 45);
    const wbgtScore = normalizeDemo(wbgt, 22, 34);
    const windScore = Math.max(0, 100 - normalizeDemo(windSpeed, 0, 15));

    const thermalStress = clampDemo(
        0.30 * temperatureScore + 0.20 * humidityScore + 0.25 * heatIndexScore + 0.15 * wbgtScore + 0.10 * windScore,
        0,
        100
    );

    const apparentScore = normalizeDemo(apparentTemperature, 25, 45);
    const healthRisk = clampDemo(
        0.40 * normalizeDemo(temperature, 25, 40) + 0.20 * humidityScore + 0.25 * thermalStress + 0.15 * apparentScore,
        0,
        100
    );

    const riskLevel = getRiskLevel(healthRisk);

    return {
        location,
        temperature,
        humidity,
        wind_speed: windSpeed,
        heat_index: heatIndex,
        wbgt,
        thermal_stress: thermalStress,
        health_risk: healthRisk,
        risk_score: healthRisk,
        risk_level: riskLevel,
        advisory: getAdvisoryText(riskLevel),
        weather_time: new Date().toISOString(),
        updated_at: new Date().toISOString()
    };
}


function getRiskLevel(score) {

    if (score < 25) return "LOW";
    if (score < 50) return "MODERATE";
    if (score < 75) return "HIGH";
    return "EXTREME";

}


function getAdvisoryText(level) {

    if (level === "LOW") {
        return "Heat conditions are currently low risk. Continue normal activities and stay hydrated.";
    }

    if (level === "MODERATE") {
        return "Moderate heat stress is possible. Drink water regularly and avoid prolonged exposure to direct sunlight.";
    }

    if (level === "HIGH") {
        return "High heat risk detected. Reduce outdoor activity, drink water regularly and take frequent breaks in cool areas.";
    }

    return "Extreme heat risk detected. Avoid unnecessary outdoor activity and remain in a cool environment. High-risk groups require special attention.";

}


/* ============================================================
   RENDER WEATHER
   ============================================================ */

function renderWeather(data) {

    const source = String(data.data_source || "Open-Meteo").toUpperCase();
    const apiLabel = document.getElementById("apiSourceLabel");

    if (apiLabel) {
        apiLabel.textContent = `API: ${source}`;
    }

    const apiSignal = document.getElementById("apiSignalDot");
    if (apiSignal) {
        apiSignal.classList.add("online");
    }

    setValue(
        "temperature",
        formatNumber(data.temperature)
    );

    setValue(
        "humidity",
        formatNumber(data.humidity)
    );

    setValue(
        "wind",
        formatNumber(data.wind_speed)
    );

    setValue(
        "heatIndex",
        formatNumber(data.heat_index)
    );

    setValue(
        "wbgt",
        formatNumber(data.wbgt)
    );

    setValue(
        "healthRisk",
        formatNumber(data.health_risk)
    );

    setValue(
        "thermalStress",
        formatNumber(data.thermal_stress)
    );


    const level =
        String(
            data.risk_level || "UNKNOWN"
        ).toUpperCase();


    document.getElementById("riskLevel")
        .textContent = level;


    document.getElementById("riskBadge")
        .textContent = level;


    const score =
        Number(data.risk_score || 0);


    document.getElementById("riskMeter")
        .style.width =
        `${Math.max(0, Math.min(100, 100 - score))}%`;


    document.getElementById("thermalBar")
        .style.width =
        `${Math.max(
            0,
            Math.min(100, Number(data.thermal_stress || 0))
        )}%`;


    document.getElementById("advisory")
        .textContent =
        data.advisory ||
        "No advisory available.";


    document.getElementById("weatherTime")
        .textContent =
        data.weather_time || "--";


    applyRiskStyle(
        document.getElementById("riskBadge"),
        level
    );

}


/* ============================================================
   HELPERS
   ============================================================ */

function setValue(id, value) {

    const element =
        document.getElementById(id);

    if (element) {
        element.textContent = value;
    }

}


function formatNumber(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "--";
    }


    const number =
        Number(value);


    if (Number.isNaN(number)) {
        return "--";
    }


    return number.toFixed(1);

}


function setLoadingState() {

    const ids = [
        "temperature",
        "humidity",
        "wind",
        "heatIndex",
        "wbgt",
        "healthRisk",
        "thermalStress"
    ];

    ids.forEach(id => {

        document.getElementById(id)
            .textContent = "...";

    });

}


/* ============================================================
   RISK STYLE
   ============================================================ */

function applyRiskStyle(element, level) {

    element.style.color = "white";

    if (level === "LOW") {

        element.style.background =
            "rgba(53,209,138,0.15)";

        element.style.color =
            "#35d18a";

    }

    else if (level === "MODERATE") {

        element.style.background =
            "rgba(255,212,71,0.15)";

        element.style.color =
            "#ffd447";

    }

    else if (level === "HIGH") {

        element.style.background =
            "rgba(255,157,61,0.15)";

        element.style.color =
            "#ff9d3d";

    }

    else if (level === "EXTREME") {

        element.style.background =
            "rgba(255,83,100,0.15)";

        element.style.color =
            "#ff5364";

    }

}


/* ============================================================
   MAP
   ============================================================ */

function initializeMap() {

    if (map) {
        return;
    }


    map =
        L.map("map")
            .setView(
                [15.3173, 75.7139],
                7
            );


    L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        {
            attribution:
                "&copy; OpenStreetMap contributors &copy; CARTO",
            subdomains: "abcd",
            maxZoom: 19
        }
    ).addTo(map);

}


/* ============================================================
   GIS
   ============================================================ */

async function loadGIS() {

    if (!map) {
        initializeMap();
    }


    const districtList =
        document.getElementById(
            "districtList"
        );


    districtList.innerHTML =
        `<div class="empty-state">
            Loading live Karnataka heat risk...
        </div>`;


    try {

        const response =
            await fetch(
                `${BACKEND_URL}/gis-risk`
            );


        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        const records =
            Array.isArray(data)
                ? data
                : data.districts || data.data || [];


        renderGIS(records);

    }

    catch (error) {

        console.warn(
            "GIS data unavailable; showing demo district view.",
            error
        );

        renderGIS(generateDemoGIS());

    }

}


async function loadHotspotList() {

    const container = document.getElementById("topRiskList");

    if (!container) {
        return;
    }

    container.innerHTML = "Loading hotspot list...";

    try {
        const response = await fetch(`${BACKEND_URL}/gis-risk`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const records = Array.isArray(data) ? data : (data.districts || data.data || []);
        const top5 = records
            .map(item => ({
                ...item,
                score: Number(item.risk_score ?? item.health_risk ?? 0),
                level: String(item.risk_level ?? item.health_level ?? "LOW").toUpperCase()
            }))
            .sort((a, b) => b.score - a.score)
            .slice(0, 5);

        renderHotspotList(top5);
    }

    catch (error) {
        console.warn("Hotspot list unavailable; using demo ranking.", error);
        const demo = generateDemoGIS()
            .map(item => ({
                ...item,
                score: Number(item.risk_score ?? item.health_risk ?? 0),
                level: String(item.risk_level ?? item.health_level ?? "LOW").toUpperCase()
            }))
            .sort((a, b) => b.score - a.score)
            .slice(0, 5);

        renderHotspotList(demo);
    }

}


function renderHotspotList(records) {

    const container = document.getElementById("topRiskList");

    if (!container) {
        return;
    }

    if (!records || records.length === 0) {
        container.innerHTML = '<div class="empty-state">No hotspot data available.</div>';
        return;
    }

    container.innerHTML = "";

    records.forEach((item, index) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "top-risk-item";

        const district = item.location || "District";
        const score = Number(item.score ?? item.risk_score ?? item.health_risk ?? 0);
        const level = String(item.level || item.risk_level || item.health_level || "LOW").toUpperCase();

        row.innerHTML = `
            <div class="top-risk-rank">#${index + 1}</div>
            <div class="top-risk-meta">
                <strong>${district}</strong>
                <small>${level} • ${score.toFixed(1)}/100</small>
            </div>
            <span class="top-risk-pill ${level.toLowerCase()}">${level}</span>
        `;

        row.addEventListener("click", () => {
            selectedDistrict = district;
            const select = document.getElementById("districtSelect");
            if (select) {
                select.value = district;
            }
            loadDashboard();
        });

        container.appendChild(row);
    });

}


const DISTRICT_NAME_ALIASES = {
    "Bengaluru Urban": "Bangalore Urban",
    "Bengaluru Rural": "Bangalore Rural",
    "Belagavi": "Belgaum",
    "Ballari": "Bellary",
    "Vijayapura": "Bijapur",
    "Chamarajanagar": "Chamrajnagar",
    "Chikkamagaluru": "Chikmagalur",
    "Shivamogga": "Shimoga",
    "Mysuru": "Mysore",
    "Tumakuru": "Tumkur"
};

function normalizeDistrictName(name) {
    const clean = String(name || "").trim();
    return DISTRICT_NAME_ALIASES[clean] || clean;
}

async function loadDistrictBoundaries() {
    if (districtBoundaryGeoJson) {
        return districtBoundaryGeoJson;
    }

    const response = await fetch(
        "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson"
    );

    if (!response.ok) {
        throw new Error(`District boundary fetch failed: ${response.status}`);
    }

    districtBoundaryGeoJson = await response.json();
    return districtBoundaryGeoJson;
}

function getBoundaryFeatureForDistrict(districtName) {
    if (!districtBoundaryGeoJson) {
        return null;
    }

    const targetName = normalizeDistrictName(districtName).toLowerCase();

    const feature = (districtBoundaryGeoJson.features || []).find(item => {
        const props = item.properties || {};
        const propName = String(props.NAME_2 || props.NAME_1 || "").trim();
        return propName && propName.toLowerCase() === targetName;
    });

    return feature || null;
}

function generateDemoGIS() {

    return districts.map((district) => {
        const latitude = 13.0 + (district.length % 6) * 0.25;
        const longitude = 75.5 + (district.length % 7) * 0.35;
        const temperature = 29 + (district.length % 12);
        const humidity = 45 + (district.length % 30);
        const windSpeed = 4 + (district.length % 14);
        const apparentTemperature = temperature + 2 + (district.length % 5);
        const heatIndex = temperature + 3 + (humidity / 100 * 8);
        const wbgt = (0.7 * temperature) + (0.2 * humidity * 0.01 * temperature) - (0.1 * windSpeed);

        const temperatureScore = normalizeDemo(temperature, 25, 42);
        const humidityScore = normalizeDemo(humidity, 35, 80);
        const heatIndexScore = normalizeDemo(heatIndex, 25, 45);
        const wbgtScore = normalizeDemo(wbgt, 22, 34);
        const windScore = Math.max(0, 100 - normalizeDemo(windSpeed, 0, 15));
        const thermalStress = clampDemo(
            0.30 * temperatureScore + 0.20 * humidityScore + 0.25 * heatIndexScore + 0.15 * wbgtScore + 0.10 * windScore,
            0,
            100
        );
        const apparentScore = normalizeDemo(apparentTemperature, 25, 45);
        const riskScore = clampDemo(
            0.40 * normalizeDemo(temperature, 25, 40) + 0.20 * humidityScore + 0.25 * thermalStress + 0.15 * apparentScore,
            0,
            100
        );

        const riskLevel = getRiskLevel(riskScore);

        return {
            location: district,
            latitude,
            longitude,
            temperature,
            humidity,
            wind_speed: windSpeed,
            heat_index: heatIndex,
            wbgt,
            thermal_stress: thermalStress,
            risk_score: riskScore,
            risk_level: riskLevel,
            health_level: riskLevel,
            health_risk: riskScore
        };

    });

}


/* ============================================================
   RENDER GIS
   ============================================================ */

async function renderGIS(records) {

    clearMapLayers();

    const districtList =
        document.getElementById(
            "districtList"
        );

    districtList.innerHTML = "";

    try {
        await loadDistrictBoundaries();
    } catch (error) {
        console.warn("District boundary dataset unavailable; falling back to centroid markers.", error);
    }

    records.forEach(item => {

        const lat =
            Number(
                item.latitude ??
                item.lat
            );

        const lon =
            Number(
                item.longitude ??
                item.lon
            );

        const score =
            Number(
                item.risk_score ??
                item.health_risk ??
                0
            );

        const level =
            String(
                item.risk_level ??
                item.health_level ??
                getRiskLevel(score)
            ).toUpperCase();

        const temperature =
            Number(
                item.temperature ??
                item.temp ??
                0
            );

        if (
            Number.isNaN(lat) ||
            Number.isNaN(lon)
        ) {
            return;
        }

        const color =
            getRiskColor(level);

        const districtFeature = getBoundaryFeatureForDistrict(item.location || "Unknown");

        let districtLayer;

        if (districtFeature && districtFeature.geometry) {
            districtLayer = L.geoJSON(districtFeature, {
                style: {
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.58,
                    weight: 2.2,
                    opacity: 1,
                    smoothFactor: 1.2
                }
            });
        } else {
            districtLayer = L.circleMarker([lat, lon], {
                radius: 10,
                color: color,
                fillColor: color,
                fillOpacity: 0.55,
                weight: 2
            });
        }

        districtLayer.bindPopup(`
            <div style="font-family:Arial;min-width:180px; color:#102033;">
                <strong style="font-size:15px">${item.location || "District"}</strong>
                <hr>
                <b>Temperature:</b> ${temperature.toFixed(1)} °C<br>
                <b>Humidity:</b> ${Number(item.humidity || 0).toFixed(1)} %<br>
                <b>Heat Index:</b> ${Number(item.heat_index || 0).toFixed(1)} °C<br>
                <b>WBGT:</b> ${Number(item.wbgt || 0).toFixed(1)} °C<br><br>
                <strong style="color:${color}">${level}</strong><br>
                Risk Score: ${score.toFixed(1)}/100
            </div>
        `);

        districtLayer.addTo(map);
        districtPolygons.push(districtLayer);

        const row =
            document.createElement("div");

        row.className =
            "district-item";

        row.innerHTML = `

            <div>

                <div class="district-name">
                    ${item.location || "Unknown"}
                </div>

                <div class="district-temp">
                    ${temperature.toFixed(1)} °C
                    • Risk ${score.toFixed(0)}
                </div>

            </div>

            <div
                class="district-risk"
                style="
                    background:${color}22;
                    color:${color};
                "
            >
                ${level}
            </div>

        `;

        row.onclick = () => {
            if (districtLayer.getBounds) {
                const bounds = districtLayer.getBounds();
                if (bounds && bounds.isValid()) {
                    map.fitBounds(bounds.pad(0.35));
                }
            } else {
                map.setView([lat, lon], 10);
            }

            districtLayer.openPopup();
        };

        districtList.appendChild(row);

    });

}


function clearMapLayers() {

    districtMarkers.forEach(
        marker => map.removeLayer(marker)
    );

    districtPolygons.forEach(
        polygon => map.removeLayer(polygon)
    );

    districtMarkers = [];
    districtPolygons = [];

}


function getRiskLevel(score) {

    if (score < 25) {
        return "LOW";
    }

    if (score < 50) {
        return "MODERATE";
    }

    if (score < 75) {
        return "HIGH";
    }

    return "EXTREME";

}


function getRiskColor(level) {

    switch (level) {

        case "LOW":
            return "#35d18a";

        case "MODERATE":
            return "#ffd447";

        case "HIGH":
            return "#ff9d3d";

        case "EXTREME":
            return "#ff5364";

        default:
            return "#7d899d";

    }

}


/* ============================================================
   FORECAST
   ============================================================ */

async async function loadForecast() {

    const container =
        document.getElementById(
            "forecastCards"
        );


    container.innerHTML =
        "Loading forecast...";


    try {

        const encoded =
            encodeURIComponent(selectedDistrict);


        const response =
            await fetch(
                `${BACKEND_URL}/forecast/${encoded}`
            );


        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        const forecast =
            Array.isArray(data)
                ? data
                : data.forecast || data.data || [];


        if (forecast && forecast.length > 0) {
            renderForecast(forecast);
            return;
        }

    }

    catch (error) {

        console.warn(
            "Forecast unavailable; showing historical workday forecast.",
            error
        );

    }

    renderForecast(generateHistoricalForecast(selectedDistrict));

}


function generateHistoricalForecast(location) {

    const baseTemp = currentWeather ? Number(currentWeather.temperature || 32) : 32;
    const baseHumidity = currentWeather ? Number(currentWeather.humidity || 58) : 58;
    const hours = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"];
    const records = [];

    hours.forEach((time, index) => {
        const factor = [0.76, 0.86, 1.08, 1.18, 1.12, 0.94][index];
        const high = baseTemp * factor + 2.5;
        const low = Math.max(18, high - 6.5 - (baseHumidity / 28));
        records.push({
            date: time,
            temperature_max: high,
            temperature_min: low,
            temperature: high,
            apparent_temperature_max: high + 2.8,
            wind_speed_max: 10 + (index * 2),
            wind_speed: 10 + (index * 2),
            hourly_label: time,
            location,
            risk_score: Math.min(100, ((high - 25) / 18) * 65 + ((baseHumidity - 25) / 65) * 25)
        });
    });

    return records;

}


/* ============================================================
   RENDER FORECAST
   ============================================================ */

function renderForecast(records) {

    const container =
        document.getElementById(
            "forecastCards"
        );


    container.innerHTML = "";


    const labels = [];

    const temperatures = [];


    records.forEach(item => {

        const date =
            item.date ||
            item.time ||
            item.hourly_label ||
            "--";


        const max =
            Number(
                item.temperature_max ??
                item.temp_max ??
                item.temperature ??
                item.temperature_2m_max ??
                0
            );


        const min =
            Number(
                item.temperature_min ??
                item.temp_min ??
                item.temperature_2m_min ??
                0
            );


        labels.push(date);

        temperatures.push(max);


        const card =
            document.createElement("div");


        card.className =
            "forecast-card";


        card.innerHTML = `

            <div class="date">
                ${date}
            </div>

            <div class="temp">
                ${max.toFixed(1)}°
            </div>

            <p>
                Minimum:
                ${min.toFixed(1)} °C
            </p>

            <p style="margin-top:6px">
                Apparent:
                ${Number(
                    item.apparent_temperature_max || 0
                ).toFixed(1)} °C
            </p>

            <p style="margin-top:6px">
                Wind:
                ${Number(
                    item.wind_speed_max || 0
                ).toFixed(1)} km/h
            </p>

        `;


        container.appendChild(card);

    });


    renderForecastChart(
        labels,
        temperatures
    );

}


/* ============================================================
   CHART
   ============================================================ */

function renderForecastChart(
    labels,
    temperatures
) {

    const canvas =
        document.getElementById(
            "forecastChart"
        );


    if (!canvas) {
        return;
    }


    if (forecastChart) {
        forecastChart.destroy();
    }


    forecastChart =
        new Chart(
            canvas,
            {
                type: "line",

                data: {

                    labels: labels,

                    datasets: [

                        {
                            label:
                                "Maximum Temperature (°C)",

                            data:
                                temperatures,

                            borderWidth: 3,

                            tension: 0.35,

                            fill: true
                        }

                    ]

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {
                            labels: {
                                color: "#aab4c4"
                            }
                        }

                    },

                    scales: {

                        x: {
                            ticks: {
                                color: "#758095"
                            },

                            grid: {
                                color:
                                    "rgba(255,255,255,0.04)"
                            }
                        },

                        y: {
                            ticks: {
                                color: "#758095"
                            },

                            grid: {
                                color:
                                    "rgba(255,255,255,0.04)"
                            }
                        }

                    }

                }

            }
        );

}


/* ============================================================
   AI ASSISTANT
   ============================================================ */

function handleAIKey(event) {

    if (event.key === "Enter") {
        sendAI();
    }

}


function askAI(question) {

    document.getElementById("aiInput")
        .value = question;

    sendAI();

}


async function sendAI() {

    const input =
        document.getElementById("aiInput");


    const question =
        input.value.trim();


    if (!question) {
        return;
    }


    addChatMessage(
        question,
        "user"
    );


    input.value = "";


    try {

        const response =
            await fetch(
                `${BACKEND_URL}/ai/chat`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: question,
                        location:
                            selectedDistrict
                    })
                }
            );


        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        const answer =
            data.answer ||
            data.response ||
            data.message ||
            "I could not generate a response.";


        addChatMessage(
            answer,
            "ai"
        );

    }

    catch (error) {

        console.warn(
            "AI backend unavailable",
            error
        );


        addChatMessage(
            generateLocalAIResponse(question),
            "ai"
        );

    }

}


function addChatMessage(
    text,
    type
) {

    const container =
        document.getElementById(
            "chatMessages"
        );


    const message =
        document.createElement("div");


    message.className =
        `message ${type}`;


    message.innerHTML = `

        <div class="avatar">
            ${type === "ai" ? "✦" : "●"}
        </div>

        <div class="bubble">
            ${text}
        </div>

    `;


    container.appendChild(message);


    container.scrollTop =
        container.scrollHeight;

}


function generateLocalAIResponse(question) {

    const q =
        question.toLowerCase();

    const temp = currentWeather ? Number(currentWeather.temperature || 32) : 32;
    const humidity = currentWeather ? Number(currentWeather.humidity || 58) : 58;

    if (
        q.includes("risk") ||
        q.includes("alert")
    ) {

        const riskLevel = getRiskLevel(((temp - 22) * 2.2) + ((humidity - 30) * 0.35));
        return `${selectedDistrict} currently shows ${riskLevel} heat risk. The strongest heat usually occurs between 12:00 and 16:00, so avoid long outdoor exposure during those hours.`;

    }

    if (
        q.includes("wbgt")
    ) {

        return "WBGT is a practical heat-stress indicator. Higher temperature and humidity together raise thermal load, especially in midday work windows.";

    }

    if (
        q.includes("precaution") ||
        q.includes("safe") ||
        q.includes("protect") ||
        q.includes("water")
    ) {

        return "Stay hydrated, reduce outdoor work during peak heat, take breaks in shaded and cool areas, and avoid strenuous activity between 12:00 and 16:00.";

    }

    if (
        q.includes("forecast") ||
        q.includes("tomorrow")
    ) {

        const historicalSeries = [
            { time: "08:00", temp: temp * 0.76 + 2.5 },
            { time: "10:00", temp: temp * 0.86 + 2.5 },
            { time: "12:00", temp: temp * 1.08 + 2.5 },
            { time: "14:00", temp: temp * 1.18 + 2.5 },
            { time: "16:00", temp: temp * 1.12 + 2.5 },
            { time: "18:00", temp: temp * 0.94 + 2.5 }
        ];
        const historicalPeak = historicalSeries.reduce((max, item) => item.temp > max.temp ? item : max, historicalSeries[0]);

        return `The historical Indian working-hours pattern suggests the peak is around ${historicalPeak.time} with a high near ${historicalPeak.temp.toFixed(1)}°C. This is used as a practical guide together with live weather data.`;

    }


    return `I am monitoring ${selectedDistrict}. Ask me about current risk, thermal stress, prediction timing, or safety steps for hot working hours.`;

}
}


/* ============================================================
   HTML ESCAPE
   ============================================================ */

function escapeHTML(value) {

    const div =
        document.createElement("div");

    div.textContent = value;

    return div.innerHTML;

}


/* ============================================================
   EMERGENCY ALERT
   ============================================================ */

function triggerEmergencyAlert() {

    const modal =
        document.getElementById(
            "emergencyModal"
        );


    document.getElementById(
        "alertDistrict"
    ).textContent =
        selectedDistrict;


    modal.classList.add("show");


    addAlertRecord();

}


function closeEmergencyAlert() {

    document.getElementById(
        "emergencyModal"
    ).classList.remove("show");

}


function addAlertRecord() {

    const container =
        document.getElementById(
            "alertHistory"
        );


    const empty =
        container.querySelector(
            ".empty-state"
        );


    if (empty) {
        empty.remove();
    }


    const record =
        document.createElement("div");


    record.className =
        "alert-record";


    const now =
        new Date()
            .toLocaleTimeString();


    record.innerHTML = `

        <strong>
            🚨 Heat Emergency Alert
        </strong>

        <br>

        District:
        ${escapeHTML(selectedDistrict)}

        <br>

        Issued:
        ${now}

        <br>

        <span style="color:#ff6571">
            Temporary demonstration alert
        </span>

    `;


    container.prepend(record);

}
