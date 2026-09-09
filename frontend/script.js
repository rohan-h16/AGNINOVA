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
let autoRefreshTimer = null;

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


function generateDemoWeather(location) {

    const seed = location
        .split("")
        .reduce((total, char) => total + char.charCodeAt(0), 0);

    const temperature = 31 + (seed % 12);
    const humidity = 48 + (seed % 33);
    const windSpeed = 6 + (seed % 18);
    const apparentTemperature = temperature + 3 + (seed % 5);
    const heatIndex = temperature + 4 + (humidity / 100 * 9);
    const wbgt = (0.7 * temperature) + (0.2 * humidity * 0.01 * temperature) - (0.1 * windSpeed);
    const thermalStress = Math.min(100, Math.max(0, 35 + (temperature * 1.4) + (humidity * 0.35) - (windSpeed * 0.7)));
    const healthRisk = Math.min(100, Math.max(0, 18 + (temperature * 1.7) + (humidity * 0.45) + (heatIndex * 0.25) - (windSpeed * 0.5)));

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
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            attribution:
                "&copy; OpenStreetMap contributors"
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


function generateDemoGIS() {

    return districts.map((district, index) => {

        const base = index + 1;
        const temperature = 29 + (base % 12);
        const humidity = 45 + (base % 30);
        const heatIndex = temperature + 3 + (humidity / 100 * 8);
        const wbgt = temperature + (humidity / 100 * 6);
        const riskScore = Math.min(100, 18 + (temperature * 1.6) + (humidity * 0.45) + (index * 0.9));

        return {
            location: district,
            latitude: 12.5 + (index % 8) * 0.6,
            longitude: 74.2 + (index % 10) * 0.8,
            temperature,
            humidity,
            heat_index: heatIndex,
            wbgt,
            risk_score: riskScore,
            risk_level: getRiskLevel(riskScore),
            health_level: getRiskLevel(riskScore)
        };

    });

}


/* ============================================================
   RENDER GIS
   ============================================================ */

function renderGIS(records) {

    clearMarkers();


    const districtList =
        document.getElementById(
            "districtList"
        );


    districtList.innerHTML = "";


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


        const marker =
            L.circleMarker(
                [lat, lon],
                {
                    radius: 10,

                    color: color,

                    fillColor: color,

                    fillOpacity: 0.75,

                    weight: 2
                }
            );


        marker.bindPopup(`

            <div style="font-family:Arial;min-width:180px">

                <strong style="font-size:15px">
                    ${item.location || "District"}
                </strong>

                <hr>

                <b>Temperature:</b>
                ${temperature.toFixed(1)} °C

                <br>

                <b>Humidity:</b>
                ${Number(item.humidity || 0).toFixed(1)} %

                <br>

                <b>Heat Index:</b>
                ${Number(item.heat_index || 0).toFixed(1)} °C

                <br>

                <b>WBGT:</b>
                ${Number(item.wbgt || 0).toFixed(1)} °C

                <br><br>

                <strong style="color:${color}">
                    ${level}
                </strong>

                <br>

                Risk Score:
                ${score.toFixed(1)}/100

            </div>

        `);


        marker.addTo(map);

        districtMarkers.push(marker);


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

            map.setView(
                [lat, lon],
                10
            );

            marker.openPopup();

        };


        districtList.appendChild(row);

    });

}


function clearMarkers() {

    districtMarkers.forEach(
        marker => map.removeLayer(marker)
    );

    districtMarkers = [];

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

async function loadForecast() {

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


        renderForecast(forecast);

    }

    catch (error) {

        console.warn(
            "Forecast unavailable; showing demo forecast.",
            error
        );

        renderForecast(generateDemoForecast());

    }

}


function generateDemoForecast() {

    const today = new Date();
    const records = [];

    for (let index = 0; index < 5; index += 1) {
        const day = new Date(today);
        day.setDate(today.getDate() + index);

        const max = 30 + ((index + 1) % 10);
        const min = 24 + (index % 5);

        records.push({
            date: day.toISOString().slice(0, 10),
            temperature_max: max,
            temperature_min: min,
            temperature: max,
            apparent_temperature_max: max + 2,
            wind_speed_max: 10 + (index % 8),
            wind_speed: 10 + (index % 8)
        });
    }

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
   =====================
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
            ${escapeHTML(text)}
        </div>

    `;


    container.appendChild(message);


    container.scrollTop =
        container.scrollHeight;

}


function generateLocalAIResponse(question) {

    const q =
        question.toLowerCase();


    if (
        q.includes("risk") &&
        currentWeather
    ) {

        return `
            ${selectedDistrict} currently has a
            ${currentWeather.risk_level || "UNKNOWN"}
            heat risk with a health-risk score of
            ${Number(
                currentWeather.health_risk || 0
            ).toFixed(0)}/100.
        `;

    }


    if (
        q.includes("wbgt")
    ) {

        return `
            WBGT stands for Wet Bulb Globe Temperature.
            It is a heat-stress indicator that considers
            environmental heat conditions. AGNINOVA uses
            an approximate prototype estimate for screening.
        `;

    }


    if (
        q.includes("precaution") ||
        q.includes("safe") ||
        q.includes("protect")
    ) {

        return `
            Stay hydrated, reduce prolonged outdoor exposure,
            take frequent breaks in cool areas, avoid strenuous
            activity during peak heat and give special attention
            to vulnerable people.
        `;

    }


    return `
        I am monitoring ${selectedDistrict}.
        Ask me about heat risk, WBGT, thermal stress,
        forecast conditions or safety precautions.
    `;

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
