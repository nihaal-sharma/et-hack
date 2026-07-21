/**
 * app.js — SafetyAI Dashboard Controller
 * Polls FastAPI endpoints, renders Leaflet map with hazard zones,
 * draws A* evacuation routes, and manages the live alert feed.
 */

// ─── Configuration ───
const API_BASE = '';
const POLL_INTERVAL = 3000;      // ms
const GRID_SIZE = 10;
const CELL_SIZE = 100;           // px per cell on the Leaflet map
const MAP_BOUNDS = [[0, 0], [GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE]];

// ─── State ───
let map = null;
let pollingTimer = null;
let isPolling = true;
let gridRectangles = {};         // key: "x,y" → Leaflet rectangle
let routePolyline = null;        // Leaflet polyline for evacuation route
let startMarker = null;
let exitMarker = null;
let exitMarkers = [];            // all exit markers
let alertCount = 0;
const MAX_ALERTS = 50;

// ─── Risk Color Map ───
const RISK_COLORS = {
    normal:   { fill: '#00e676', stroke: '#00c853', opacity: 0.15, strokeOpacity: 0.3 },
    warning:  { fill: '#ffd600', stroke: '#ffab00', opacity: 0.35, strokeOpacity: 0.6 },
    danger:   { fill: '#ff6d00', stroke: '#e65100', opacity: 0.45, strokeOpacity: 0.7 },
    critical: { fill: '#ff1744', stroke: '#d50000', opacity: 0.55, strokeOpacity: 0.8 }
};

// ─── Zone Labels ───
const ZONE_LABELS = {
    '0,0': 'Welding Bay', '0,1': 'Welding Bay', '1,0': 'Welding Bay', '1,1': 'Welding Bay',
    '8,8': 'Chemical Store', '8,9': 'Chemical Store', '9,8': 'Chemical Store', '9,9': 'Chemical Store',
    '4,0': 'Assembly Line', '5,0': 'Assembly Line', '6,0': 'Assembly Line',
    '4,1': 'Assembly Line', '5,1': 'Assembly Line', '6,1': 'Assembly Line',
    '0,8': 'Furnace Area', '0,9': 'Furnace Area', '1,8': 'Furnace Area', '1,9': 'Furnace Area',
    '7,4': 'Loading Dock', '8,4': 'Loading Dock', '9,4': 'Loading Dock',
    '7,5': 'Loading Dock', '8,5': 'Loading Dock', '9,5': 'Loading Dock'
};

// ─── Exit Nodes ───
const EXIT_NODES = [
    [0, 0], [9, 0], [0, 9], [9, 9], [4, 0], [5, 9]
];


// ═══════════════════════════════════════════════════════════════
//  INITIALIZATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initClock();
    startPolling();
    addAlert('info', 'Dashboard initialized. Connecting to sensor network...');
});


function initMap() {
    // Create Leaflet map with Simple CRS (pixel coordinates)
    map = L.map('factory-map', {
        crs: L.CRS.Simple,
        minZoom: -2,
        maxZoom: 2,
        zoomControl: true,
        attributionControl: false
    });

    // Load factory blueprint as image overlay
    const imageUrl = '/static/factory_blueprint.png';
    L.imageOverlay(imageUrl, MAP_BOUNDS).addTo(map);
    map.fitBounds(MAP_BOUNDS);

    // Draw grid cells
    for (let x = 0; x < GRID_SIZE; x++) {
        for (let y = 0; y < GRID_SIZE; y++) {
            const bounds = [
                [y * CELL_SIZE, x * CELL_SIZE],
                [(y + 1) * CELL_SIZE, (x + 1) * CELL_SIZE]
            ];

            const rect = L.rectangle(bounds, {
                color: RISK_COLORS.normal.stroke,
                fillColor: RISK_COLORS.normal.fill,
                fillOpacity: RISK_COLORS.normal.opacity,
                weight: 1,
                opacity: RISK_COLORS.normal.strokeOpacity,
                className: 'grid-cell'
            }).addTo(map);

            // Add coordinate label
            const center = [(y + 0.5) * CELL_SIZE, (x + 0.5) * CELL_SIZE];
            const zone = ZONE_LABELS[`${x},${y}`] || '';

            rect.bindPopup(createCellPopup(x, y, zone, {}));

            // Click handler for routing start point
            rect.on('click', () => {
                document.getElementById('start-x').value = x;
                document.getElementById('start-y').value = y;
            });

            gridRectangles[`${x},${y}`] = rect;
        }
    }

    // Draw exit markers
    EXIT_NODES.forEach(([ex, ey]) => {
        const center = [(ey + 0.5) * CELL_SIZE, (ex + 0.5) * CELL_SIZE];
        const exitIcon = L.divIcon({
            className: 'exit-marker',
            html: `<div style="
                width: 24px; height: 24px;
                background: rgba(0, 188, 212, 0.3);
                border: 2px solid #00bcd4;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 12px; color: #00bcd4;
                box-shadow: 0 0 10px rgba(0, 188, 212, 0.4);
            ">🚪</div>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });
        const marker = L.marker(center, { icon: exitIcon }).addTo(map);
        marker.bindTooltip(`Exit (${ex},${ey})`, {
            className: 'exit-tooltip',
            direction: 'top',
            offset: [0, -15]
        });
        exitMarkers.push(marker);
    });

    // Add grid coordinate labels on edges
    for (let i = 0; i < GRID_SIZE; i++) {
        // Bottom labels (X axis)
        L.marker([-15, (i + 0.5) * CELL_SIZE], {
            icon: L.divIcon({
                className: 'coord-label',
                html: `<span style="color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 11px;">${i}</span>`,
                iconSize: [20, 16],
                iconAnchor: [10, 8]
            })
        }).addTo(map);

        // Left labels (Y axis)
        L.marker([(i + 0.5) * CELL_SIZE, -15], {
            icon: L.divIcon({
                className: 'coord-label',
                html: `<span style="color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 11px;">${i}</span>`,
                iconSize: [20, 16],
                iconAnchor: [10, 8]
            })
        }).addTo(map);
    }
}


function createCellPopup(x, y, zone, sensors) {
    const gas = sensors.gas || {};
    const temp = sensors.temperature || {};
    const zoneBadge = zone ? `<div style="color: #7b61ff; font-size: 0.72rem; margin-bottom: 4px;">${zone}</div>` : '';

    return `
        <div style="min-width: 160px;">
            <div style="font-weight: 700; font-size: 0.9rem; margin-bottom: 2px;">
                Cell (${x}, ${y})
            </div>
            ${zoneBadge}
            <hr style="border: none; border-top: 1px solid rgba(99,179,237,0.15); margin: 6px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 3px;">
                <span style="color: #94a3b8;">Gas:</span>
                <span style="font-family: 'JetBrains Mono', monospace; color: ${(gas.value || 0) > 50 ? '#ff1744' : '#00e676'}; font-weight: 600;">
                    ${gas.value != null ? gas.value + ' ppm' : '—'}
                </span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="color: #94a3b8;">Temp:</span>
                <span style="font-family: 'JetBrains Mono', monospace; color: ${(temp.value || 0) > 65 ? '#ff6d00' : '#00e676'}; font-weight: 600;">
                    ${temp.value != null ? temp.value + ' °C' : '—'}
                </span>
            </div>
        </div>
    `;
}


function initClock() {
    function update() {
        const now = new Date();
        document.getElementById('live-clock').textContent = now.toLocaleTimeString('en-US', { hour12: false });
    }
    update();
    setInterval(update, 1000);
}


// ═══════════════════════════════════════════════════════════════
//  DATA POLLING
// ═══════════════════════════════════════════════════════════════

function startPolling() {
    fetchSensorData();
    pollingTimer = setInterval(fetchSensorData, POLL_INTERVAL);
}

function stopPolling() {
    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
    }
}

function togglePolling() {
    isPolling = !isPolling;
    const label = document.getElementById('polling-label');
    const btn = document.getElementById('btn-toggle-polling');

    if (isPolling) {
        startPolling();
        label.textContent = 'Pause Live Updates';
        btn.querySelector('.btn-icon').textContent = '⏸️';
        addAlert('info', 'Live updates resumed.');
    } else {
        stopPolling();
        label.textContent = 'Resume Live Updates';
        btn.querySelector('.btn-icon').textContent = '▶️';
        addAlert('info', 'Live updates paused.');
    }
}


async function fetchSensorData() {
    try {
        const res = await fetch(`${API_BASE}/api/sensors`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        updateGrid(data);
        updateStats(data);
    } catch (err) {
        console.error('Sensor fetch error:', err);
    }
}


function updateGrid(data) {
    if (!data.grid) return;

    data.grid.forEach(cell => {
        const key = `${cell.grid_x},${cell.grid_y}`;
        const rect = gridRectangles[key];
        if (!rect) return;

        const risk = cell.risk_level || 'normal';
        const colors = RISK_COLORS[risk] || RISK_COLORS.normal;

        rect.setStyle({
            fillColor: colors.fill,
            color: colors.stroke,
            fillOpacity: colors.opacity,
            opacity: colors.strokeOpacity
        });

        // Update popup content
        const zone = ZONE_LABELS[key] || '';
        rect.setPopupContent(createCellPopup(cell.grid_x, cell.grid_y, zone, cell.sensors));

        // Add permit markers if any
        if (cell.permits && cell.permits.length > 0) {
            // Visual indicator for permits (thicker border)
            rect.setStyle({
                ...rect.options,
                weight: 3,
                dashArray: '5,5'
            });
        } else {
            rect.setStyle({
                ...rect.options,
                weight: 1,
                dashArray: null
            });
        }
    });
}


function updateStats(data) {
    const grid = data.grid || [];

    let critical = 0, danger = 0, warning = 0, normal = 0;
    grid.forEach(cell => {
        switch (cell.risk_level) {
            case 'critical': critical++; break;
            case 'danger': danger++; break;
            case 'warning': warning++; break;
            default: normal++; break;
        }
    });

    animateNumber('stat-critical', critical);
    animateNumber('stat-danger', danger);
    animateNumber('stat-warning', warning);
    animateNumber('stat-normal', normal);

    document.getElementById('active-readings').textContent = data.total_sensors || '—';
    document.getElementById('active-permits').textContent = data.active_permits || '—';

    const now = new Date();
    document.getElementById('last-update').textContent = now.toLocaleTimeString('en-US', { hour12: false });

    // Update overall risk badge
    const badge = document.getElementById('overall-risk-badge');
    if (critical > 0) {
        setBadge(badge, 'CRITICAL', 'critical');
    } else if (danger > 0) {
        setBadge(badge, 'DANGER', 'danger');
    } else if (warning > 0) {
        setBadge(badge, 'WARNING', 'warning');
    } else {
        setBadge(badge, 'NORMAL', 'normal');
    }

    // Update system status bar
    const statusBadge = document.getElementById('system-status');
    if (critical > 0) {
        statusBadge.querySelector('span:last-child').textContent = 'CRITICAL ALERT';
        statusBadge.style.background = 'rgba(255, 23, 68, 0.15)';
        statusBadge.style.borderColor = 'rgba(255, 23, 68, 0.3)';
        statusBadge.style.color = '#ff1744';
        statusBadge.querySelector('.pulse-dot').style.background = '#ff1744';
    } else {
        statusBadge.querySelector('span:last-child').textContent = 'SYSTEM ONLINE';
        statusBadge.style.background = 'rgba(0, 230, 118, 0.12)';
        statusBadge.style.borderColor = 'rgba(0, 230, 118, 0.3)';
        statusBadge.style.color = '#00e676';
        statusBadge.querySelector('.pulse-dot').style.background = '#00e676';
    }
}


function animateNumber(statId, value) {
    const el = document.getElementById(statId);
    if (!el) return;
    const numEl = el.querySelector('.stat-number');
    if (numEl) numEl.textContent = value;
}


function setBadge(el, text, level) {
    el.textContent = text;
    el.className = `badge ${level}`;
}


// ═══════════════════════════════════════════════════════════════
//  RISK EVALUATION
// ═══════════════════════════════════════════════════════════════

async function triggerRiskEvaluation() {
    const btn = document.getElementById('btn-evaluate-risk');
    btn.classList.add('loading');
    btn.textContent = '  Evaluating...';

    addAlert('info', 'AI risk evaluation started...');

    try {
        const res = await fetch(`${API_BASE}/api/evaluate_risk`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        displayRiskResults(data);

        // Auto-find route if hazards detected
        if (data.hazardous_nodes && data.hazardous_nodes.length > 0) {
            findEvacuationRoute();
        }

    } catch (err) {
        console.error('Risk evaluation error:', err);
        addAlert('danger', `Risk evaluation failed: ${err.message}`);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="btn-icon">🔍</span> Evaluate Risk';
    }
}


function displayRiskResults(data) {
    const risks = data.risk_assessment?.compound_risks || [];
    const hazards = data.hazardous_nodes || [];

    // Update alerts feed
    if (data.summary) {
        const level = data.risk_assessment?.critical_count > 0 ? 'critical' :
                      data.risk_assessment?.high_count > 0 ? 'danger' :
                      risks.length > 0 ? 'warning' : 'info';
        addAlert(level, data.summary);
    }

    // Show compound risks panel
    const riskCard = document.getElementById('compound-risk-card');
    const riskList = document.getElementById('compound-risks-list');

    if (risks.length > 0) {
        riskCard.classList.remove('hidden');
        riskList.innerHTML = '';

        risks.forEach(risk => {
            const item = document.createElement('div');
            item.className = `compound-risk-item ${risk.risk_level}`;
            item.innerHTML = `
                <div class="risk-type">${risk.compound_type} — Cell (${risk.grid_x},${risk.grid_y})</div>
                <div class="risk-desc">${risk.description}</div>
                <div class="risk-action">⚡ ${risk.recommended_action}</div>
            `;
            riskList.appendChild(item);
        });

        // Add individual hazard alerts
        risks.forEach(risk => {
            addAlert(
                risk.risk_level === 'CRITICAL' ? 'critical' : 'danger',
                `${risk.compound_type} at (${risk.grid_x},${risk.grid_y}): ${risk.description.substring(0, 100)}...`
            );
        });
    } else {
        riskCard.classList.add('hidden');
        addAlert('info', '✅ No compound risks detected. Factory operations normal.');
    }
}


// ═══════════════════════════════════════════════════════════════
//  EVACUATION ROUTING
// ═══════════════════════════════════════════════════════════════

async function findEvacuationRoute() {
    const startX = parseInt(document.getElementById('start-x').value) || 5;
    const startY = parseInt(document.getElementById('start-y').value) || 5;

    const btn = document.getElementById('btn-find-route');
    btn.classList.add('loading');

    try {
        const res = await fetch(`${API_BASE}/api/evacuation_route?start_x=${startX}&start_y=${startY}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        drawEvacuationRoute(data);
        updateRouteInfo(data);

        if (data.status === 'route_found') {
            addAlert('info', `🚪 Evacuation route found: ${data.steps} steps via ${data.algorithm} to exit (${data.exit_node.join(',')})`);
        } else if (data.error) {
            addAlert('danger', `⛔ ${data.error}`);
        }

    } catch (err) {
        console.error('Route error:', err);
        addAlert('danger', `Route calculation failed: ${err.message}`);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="btn-icon">🚨</span> Find Evacuation Route';
    }
}


function drawEvacuationRoute(data) {
    // Clear previous route
    if (routePolyline) {
        map.removeLayer(routePolyline);
        routePolyline = null;
    }
    if (startMarker) {
        map.removeLayer(startMarker);
        startMarker = null;
    }
    if (exitMarker) {
        map.removeLayer(exitMarker);
        exitMarker = null;
    }

    if (!data.path || data.path.length === 0) return;

    // Convert grid coords to pixel coords (center of each cell)
    const latLngs = data.path.map(([x, y]) => [
        (y + 0.5) * CELL_SIZE,
        (x + 0.5) * CELL_SIZE
    ]);

    // Draw animated route polyline
    routePolyline = L.polyline(latLngs, {
        color: '#00f0ff',
        weight: 4,
        opacity: 0.9,
        dashArray: '10,8',
        lineCap: 'round',
        lineJoin: 'round',
        className: 'route-line'
    }).addTo(map);

    // Add a glow effect layer
    const glowLine = L.polyline(latLngs, {
        color: '#7b61ff',
        weight: 8,
        opacity: 0.25,
        lineCap: 'round',
        lineJoin: 'round'
    }).addTo(map);

    // Store glow reference for cleanup
    routePolyline._glowLine = glowLine;

    // Start marker (person icon)
    const startCoord = latLngs[0];
    startMarker = L.marker(startCoord, {
        icon: L.divIcon({
            className: 'route-marker',
            html: `<div style="
                width: 30px; height: 30px;
                background: linear-gradient(135deg, #00f0ff, #7b61ff);
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 16px;
                box-shadow: 0 0 15px rgba(0, 240, 255, 0.6);
                animation: pulse 1.5s infinite;
            ">🧑</div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        })
    }).addTo(map);
    startMarker.bindTooltip(`Start (${data.start.join(',')})`, { direction: 'top', offset: [0, -18] });

    // Exit marker
    const exitCoord = latLngs[latLngs.length - 1];
    exitMarker = L.marker(exitCoord, {
        icon: L.divIcon({
            className: 'route-marker',
            html: `<div style="
                width: 30px; height: 30px;
                background: linear-gradient(135deg, #00e676, #00bcd4);
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 16px;
                box-shadow: 0 0 15px rgba(0, 230, 118, 0.6);
            ">✅</div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        })
    }).addTo(map);
    exitMarker.bindTooltip(`Exit (${data.exit_node.join(',')})`, { direction: 'top', offset: [0, -18] });

    // Fit map to show full route
    map.fitBounds(routePolyline.getBounds().pad(0.2));

    // Animate dash offset
    animateRoute();
}


function animateRoute() {
    // CSS-based dash animation
    const style = document.createElement('style');
    style.textContent = `
        .route-line {
            animation: dashMove 1s linear infinite;
        }
        @keyframes dashMove {
            to { stroke-dashoffset: -18; }
        }
    `;
    document.head.appendChild(style);
}


function updateRouteInfo(data) {
    const card = document.getElementById('evacuation-card');
    card.classList.remove('hidden');

    document.getElementById('route-algorithm').textContent = data.algorithm || '—';
    document.getElementById('route-distance').textContent = data.distance ? `${data.distance} units` : '—';
    document.getElementById('route-steps').textContent = data.steps || '—';
    document.getElementById('route-exit').textContent = data.exit_node ? `(${data.exit_node.join(',')})` : '—';
}


// ═══════════════════════════════════════════════════════════════
//  ALERT MANAGEMENT
// ═══════════════════════════════════════════════════════════════

function addAlert(level, message) {
    const feed = document.getElementById('alerts-feed');
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false });

    const item = document.createElement('div');
    item.className = `alert-item ${level}`;
    item.innerHTML = `
        <span class="alert-time">${time}</span>
        <span class="alert-msg">${message}</span>
    `;

    // Prepend (newest on top)
    feed.insertBefore(item, feed.firstChild);
    alertCount++;

    // Cap alerts
    while (feed.children.length > MAX_ALERTS) {
        feed.removeChild(feed.lastChild);
    }
}


function clearAlerts() {
    const feed = document.getElementById('alerts-feed');
    feed.innerHTML = '';
    alertCount = 0;
    addAlert('info', 'Alerts cleared.');
}


// ═══════════════════════════════════════════════════════════════
//  CLEANUP
// ═══════════════════════════════════════════════════════════════

window.addEventListener('beforeunload', () => {
    stopPolling();
});
