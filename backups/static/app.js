const BIOME_COLORS = {
    0: "#FFFF00", 1: "#228B22", 2: "#00FFFF", 3: "#DAA520", 
    4: "#6B8E23", 5: "#2F4F4F", 6: "#8B4513", 7: "#FF4500", 
    8: "#FFFAFA", 9: "#20B2AA", 10: "#0000CD", 11: "#000080", 
    12: "#000033", 13: "#4B0082"
};

let mapData = { hexes: [], settlements: [], entities: [] };
let minQ = 0, maxQ = 0, minR = 0, maxR = 0;
let gridWidth = 0, gridHeight = 0;

// Viewport settings
let viewportX = 0, viewportY = 0;
let zoomLevel = 15; // Pixels per hex in main map

const miniCanvas = document.getElementById('minimap');
const miniCtx = miniCanvas.getContext('2d');
const mainCanvas = document.getElementById('mainmap');
const mainCtx = mainCanvas.getContext('2d');

// --- Initialization ---

async function fetchMap() {
    document.getElementById('status').innerText = "Loading map...";
    const res = await fetch('/api/map');
    mapData = await res.json();
    
    if (mapData.hexes.length > 0) {
        minQ = Math.min(...mapData.hexes.map(h => h.q));
        maxQ = Math.max(...mapData.hexes.map(h => h.q));
        minR = Math.min(...mapData.hexes.map(h => h.r));
        maxR = Math.max(...mapData.hexes.map(h => h.r));
        gridWidth = maxQ - minQ + 1;
        gridHeight = maxR - minR + 1;
        
        // Center viewport initially
        viewportX = gridWidth / 2 * zoomLevel;
        viewportY = gridHeight / 2 * zoomLevel;
    }
    
    drawMiniMap();
    drawMainMap();
    fetchStatus();
    fetchLogs();
    document.getElementById('status').innerText = "Ready.";
}

function getHexColor(hex) {
    let biome = hex.pack_geo & 0xF;
    return BIOME_COLORS[biome] || "#333";
}

// --- Drawing ---

function drawMiniMap() {
    miniCtx.clearRect(0, 0, miniCanvas.width, miniCanvas.height);
    
    const scaleX = miniCanvas.width / gridWidth;
    const scaleY = miniCanvas.height / gridHeight;
    
    for (let hex of mapData.hexes) {
        miniCtx.fillStyle = getHexColor(hex);
        miniCtx.fillRect((hex.q - minQ) * scaleX, (hex.r - minR) * scaleY, scaleX + 1, scaleY + 1);
    }
    
    // Draw Viewport Box
    const viewW = (mainCanvas.width / zoomLevel) * scaleX;
    const viewH = (mainCanvas.height / zoomLevel) * scaleY;
    const viewX = (viewportX / zoomLevel) * scaleX - viewW / 2;
    const viewY = (viewportY / zoomLevel) * scaleY - viewH / 2;
    
    miniCtx.strokeStyle = "red";
    miniCtx.lineWidth = 2;
    miniCtx.strokeRect(viewX, viewY, viewW, viewH);
}

function drawMainMap() {
    // Handle resizing natively
    mainCanvas.width = mainCanvas.parentElement.clientWidth;
    mainCanvas.height = mainCanvas.parentElement.clientHeight;
    
    mainCtx.clearRect(0, 0, mainCanvas.width, mainCanvas.height);
    
    const hexSize = zoomLevel;
    const w3 = Math.sqrt(3) * hexSize;
    const h32 = 1.5 * hexSize;
    
    // Offset so viewportX/Y is at center of canvas
    const offsetX = mainCanvas.width / 2 - viewportX;
    const offsetY = mainCanvas.height / 2 - viewportY;
    
    const settlementsByHex = {};
    for (let s of mapData.settlements) settlementsByHex[s.global_hex_id] = s;
    
    const entitiesByHex = {};
    for (let e of mapData.entities) {
        if (!entitiesByHex[e.global_hex_id]) entitiesByHex[e.global_hex_id] = [];
        entitiesByHex[e.global_hex_id].push(e);
    }

    // Sort to draw background then icons
    for (let hex of mapData.hexes) {
        // Hex grid math (axial to pixel)
        // Using standard flat-topped hexes or just squares for simplicity
        // The user liked the "raw array" look earlier, but let's do real hexes.
        // Wait, user said "just use icon s to show trees mountains". We will just render squares to match the un-skewed 2D DB grid.
        
        const px = (hex.q - minQ) * hexSize + offsetX;
        const py = (hex.r - minR) * hexSize + offsetY;
        
        // Culling
        if (px < -hexSize || px > mainCanvas.width || py < -hexSize || py > mainCanvas.height) continue;
        
        mainCtx.fillStyle = getHexColor(hex);
        mainCtx.fillRect(px, py, hexSize, hexSize);
        mainCtx.strokeStyle = "rgba(0,0,0,0.1)";
        mainCtx.strokeRect(px, py, hexSize, hexSize);
        
        // Icons
        let text = "";
        let biome = hex.pack_geo & 0xF;
        if (biome === 1 || biome === 3) text = "🌲";
        if (biome === 6) text = "⛰️";
        if (biome === 7) text = "🌋";
        
        // Settlement
        if (settlementsByHex[hex.id]) text = "🏰";
        
        // Entities (Chaos, Storms)
        if (entitiesByHex[hex.id]) {
            let e = entitiesByHex[hex.id][0];
            if (e.type === "Hurricane" || e.type === "Chaos Storm") text = "🌪️";
            if (e.type === "Chaos Creature" || e.type === "Cult Monster") text = "🦑";
        }
        
        if (text) {
            mainCtx.font = `${hexSize * 0.8}px Arial`;
            mainCtx.textAlign = "center";
            mainCtx.textBaseline = "middle";
            mainCtx.fillText(text, px + hexSize/2, py + hexSize/2);
        }
    }
}

// --- Interaction ---

miniCanvas.addEventListener('mousedown', (e) => {
    const rect = miniCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const scaleX = miniCanvas.width / gridWidth;
    const scaleY = miniCanvas.height / gridHeight;
    
    viewportX = (x / scaleX) * zoomLevel;
    viewportY = (y / scaleY) * zoomLevel;
    
    drawMiniMap();
    drawMainMap();
});

let isDragging = false;
let lastMouseX = 0;
let lastMouseY = 0;

mainCanvas.addEventListener('mousedown', (e) => {
    isDragging = true;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
});
window.addEventListener('mouseup', () => isDragging = false);
window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - lastMouseX;
    const dy = e.clientY - lastMouseY;
    viewportX -= dx;
    viewportY -= dy;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    drawMiniMap();
    drawMainMap();
});

// Click Handling
mainCanvas.addEventListener('click', (e) => {
    if (isDragging && (Math.abs(e.clientX - lastMouseX) > 2)) return; // Was a drag
    handleMapClick(e, false);
});
mainCanvas.addEventListener('dblclick', (e) => {
    handleMapClick(e, true);
});

async function handleMapClick(e, isDouble) {
    const rect = mainCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const offsetX = mainCanvas.width / 2 - viewportX;
    const offsetY = mainCanvas.height / 2 - viewportY;
    
    const gridX = Math.floor((x - offsetX) / zoomLevel);
    const gridY = Math.floor((y - offsetY) / zoomLevel);
    
    const q = gridX + minQ;
    const r = gridY + minR;
    
    if (isDouble) {
        document.getElementById('cluster-content').innerText = "Loading...";
        const res = await fetch(`/api/cluster/${q}/${r}`);
        const data = await res.json();
        renderCluster(data);
    } else {
        document.getElementById('hex-content').innerText = "Loading...";
        const res = await fetch(`/api/hex/${q}/${r}`);
        if (res.status === 404) {
            document.getElementById('hex-content').innerText = "Hex not found in DB.";
        } else {
            const data = await res.json();
            renderHex(data, q, r);
        }
    }
}

function renderHex(data, q, r) {
    let html = `<strong>Coordinates:</strong> q=${q}, r=${r}<br>`;
    html += `<strong>Biome ID:</strong> ${data.biome}<br>`;
    html += `<strong>Elevation:</strong> ${data.elevation}<br>`;
    html += `<strong>Lake:</strong> ${data.is_lake ? "Yes" : "No"}<br>`;
    if (data.chaos_domain) html += `<strong style="color:red">Chaos Domain: ${data.chaos_domain}</strong><br>`;
    
    if (data.settlement) {
        html += `<hr>`;
        html += `<strong>🏰 ${data.settlement.name}</strong><br>`;
        html += `Pop: ${data.settlement.population.toFixed(0)} | Wealth: ${data.settlement.wealth.toFixed(0)} | Sec: ${data.settlement.security_points.toFixed(0)}<br>`;
    }
    
    document.getElementById('hex-content').innerHTML = html;
}

function renderCluster(data) {
    let html = `<strong>Center:</strong> q=${data.center_q}, r=${data.center_r}<br>`;
    html += `<strong>Settlements:</strong> ${data.settlements.length}<br>`;
    html += `<strong>Total Pop:</strong> ${data.total_population.toFixed(0)}<br>`;
    html += `<strong>Total Wealth:</strong> ${data.total_wealth.toFixed(0)}<br>`;
    
    let facs = new Set(data.settlements.map(s => s.f_name));
    html += `<strong>Factions:</strong><ul>`;
    for (let f of facs) if (f) html += `<li>${f}</li>`;
    html += `</ul>`;
    
    document.getElementById('cluster-content').innerHTML = html;
}

// --- Controls ---

const tickSlider = document.getElementById('tickSlider');
tickSlider.addEventListener('input', () => {
    document.getElementById('tickValue').innerText = tickSlider.value;
});

document.getElementById('runBtn').addEventListener('click', async () => {
    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerText = "Running...";
    
    const ticks = parseInt(tickSlider.value);
    await fetch('/api/tick', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ticks: ticks})
    });
    
    // Sync map and logs
    await fetchMap();
    btn.disabled = false;
    btn.innerText = "▶ Run Simulation";
});

async function fetchStatus() {
    const res = await fetch('/api/status');
    const data = await res.json();
    document.getElementById('status').innerHTML = `<strong>Tick:</strong> ${data.tick} | <strong>Season:</strong> ${data.season} | <strong>Pop:</strong> ${data.global_population}`;
}

async function fetchLogs() {
    const res = await fetch('/api/logs');
    const logs = await res.json();
    let html = "";
    for (let log of logs) {
        html += `<div class="log-entry">[Tick ${log.tick}] <span class="log-category log-${log.category}">${log.category}</span> ${log.message}</div>`;
    }
    document.getElementById('logs').innerHTML = html;
}

window.addEventListener('resize', drawMainMap);

// Init
fetchMap();
setInterval(fetchLogs, 5000); // Poll logs just in case
setInterval(fetchStatus, 5000);
