const BIOME_COLORS = {
    0: "#FFFF00", 1: "#228B22", 2: "#00FFFF", 3: "#DAA520", 
    4: "#6B8E23", 5: "#2F4F4F", 6: "#8B4513", 7: "#FF4500", 
    8: "#FFFAFA", 9: "#20B2AA", 10: "#0000CD", 11: "#000080", 
    12: "#000033", 13: "#4B0082"
};

const BIOME_NAMES = {
    0: "Jungle", 1: "Forest", 2: "Taiga", 3: "Desert",
    4: "Plains", 5: "Tundra", 6: "Mountains", 7: "Volcano",
    8: "Arctic", 9: "Ocean", 10: "Coral Reef", 11: "Arctic Ocean",
    12: "Abyssal Trench"
};

let mapData = { hexes: [], settlements: [], entities: [] };
let minQ = 0, maxQ = 0, minR = 0, maxR = 0;
let minPx = 0, maxPx = 0, minPy = 0, maxPy = 0;

// Viewport settings
let viewportX = 0, viewportY = 0;
let zoomLevel = 15; // Pixels per hex in main map

const miniCanvas = document.getElementById('minimap');
const miniCtx = miniCanvas.getContext('2d');
const mainCanvas = document.getElementById('mainmap');
const mainCtx = mainCanvas.getContext('2d');
const microCanvas = document.getElementById('microcanvas');
const microCtx = microCanvas.getContext('2d');
let currentMicroData = null;

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
        
        minPx = Infinity; maxPx = -Infinity; minPy = Infinity; maxPy = -Infinity;
        for (let h of mapData.hexes) {
            const px = Math.sqrt(3) * (h.q + h.r / 2);
            const py = -1.5 * h.r;
            if (px < minPx) minPx = px;
            if (px > maxPx) maxPx = px;
            if (py < minPy) minPy = py;
            if (py > maxPy) maxPy = py;
        }
        
        // Center viewport initially
        viewportX = ((maxPx + minPx) / 2) * zoomLevel;
        viewportY = ((maxPy + minPy) / 2) * zoomLevel;
    }
    
    drawMiniMap();
    drawMainMap();
    fetchStatus();
    fetchLogs();
    document.getElementById('status').innerText = "Ready.";
}

function hashColor(id) {
    let hash = (id * 2654435761) % Math.pow(2, 32);
    let color = "#" + (hash & 0x00FFFFFF).toString(16).padStart(6, '0');
    return color;
}

function getHexColor(hex, settlementsByHex) {
    let overlay = document.getElementById('overlaySelect') ? document.getElementById('overlaySelect').value : "biome";
    
    if (overlay === "biome" || overlay === "weather") {
        let biome = hex.pack_geo & 0xF;
        return BIOME_COLORS[biome] || "#333";
    }
    
    if (overlay === "ecology_p1") {
        let p1 = hex.pack_ecology & 0xFF;
        return `rgb(0, ${p1}, 0)`;
    }
    if (overlay === "ecology_p2") {
        let p2 = (hex.pack_ecology >> 8) & 0xFF;
        return `rgb(${p2}, ${Math.floor(p2*0.6)}, 0)`;
    }
    if (overlay === "ecology_p3") {
        let p3 = (hex.pack_ecology >> 16) & 0xFF;
        return `rgb(${p3}, 0, 0)`;
    }
    
    let s = settlementsByHex[hex.id];
    if (!s) return "#111"; // Empty hexes are dark for settlement-specific overlays
    
    if (overlay === "faction") {
        return hashColor(s.faction_id);
    }
    if (overlay === "population") {
        let intensity = Math.min(255, Math.floor((s.population / 2000) * 255));
        return `rgb(${intensity}, 0, ${255 - intensity})`;
    }
    if (overlay === "wealth") {
        let intensity = Math.min(255, Math.floor((s.wealth / 5000) * 255));
        return `rgb(${intensity}, ${Math.floor(intensity*0.8)}, 0)`;
    }
    return "#333";
}

// --- Drawing ---

function drawMiniMap() {
    miniCtx.clearRect(0, 0, miniCanvas.width, miniCanvas.height);
    
    if (mapData.hexes.length === 0) return;
    
    const scaleX = miniCanvas.width / (maxPx - minPx || 1);
    const scaleY = miniCanvas.height / (maxPy - minPy || 1);
    const scale = Math.min(scaleX, scaleY) * 0.9;
    
    const ox = (miniCanvas.width - (maxPx - minPx) * scale) / 2;
    const oy = (miniCanvas.height - (maxPy - minPy) * scale) / 2;
    
    for (let hex of mapData.hexes) {
        const px = Math.sqrt(3) * (hex.q + hex.r / 2);
        const py = -1.5 * hex.r;
        
        const drawX = ox + (px - minPx) * scale;
        const drawY = oy + (py - minPy) * scale;
        
        miniCtx.fillStyle = getHexColor(hex, {}); // Mini map is always biome
        miniCtx.fillRect(drawX, drawY, Math.max(1, scale * 1.5), Math.max(1, scale * 1.5));
    }
    
    // Draw Viewport Box
    const viewW = (mainCanvas.width / zoomLevel) * scale;
    const viewH = (mainCanvas.height / zoomLevel) * scale;
    const viewX = ox + (viewportX / zoomLevel - minPx) * scale - viewW / 2;
    const viewY = oy + (viewportY / zoomLevel - minPy) * scale - viewH / 2;
    
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
    
    const weatherByHex = {};
    if (mapData.weather) {
        for (let w of mapData.weather) {
            let key = `${w.global_q},${w.global_r}`;
            if (!weatherByHex[key]) weatherByHex[key] = [];
            weatherByHex[key].push(w);
        }
    }

    // Sort to draw background then icons
    for (let hex of mapData.hexes) {
        const px = offsetX + w3 * (hex.q + hex.r / 2);
        const py = offsetY - h32 * hex.r; // negative r

        if (px < -hexSize || px > mainCanvas.width + hexSize || 
            py < -hexSize || py > mainCanvas.height + hexSize) continue;

        mainCtx.fillStyle = getHexColor(hex, settlementsByHex);
        
        // Draw Hexagon
        mainCtx.beginPath();
        for (let i = 0; i < 6; i++) {
            let angle_deg = 60 * i - 30;
            let angle_rad = Math.PI / 180 * angle_deg;
            let hx = px + hexSize * Math.cos(angle_rad);
            let hy = py + hexSize * Math.sin(angle_rad);
            if (i === 0) mainCtx.moveTo(hx, hy);
            else mainCtx.lineTo(hx, hy);
        }
        mainCtx.closePath();
        mainCtx.fill();
        
        mainCtx.strokeStyle = "rgba(0,0,0,0.1)";
        mainCtx.stroke();
        
        // Draw Lakes & Rivers
        if (hex.is_lake) {
            mainCtx.fillStyle = "cyan";
            mainCtx.beginPath();
            mainCtx.arc(px, py, hexSize * 0.4, 0, Math.PI * 2);
            mainCtx.fill();
        } else if (hex.river_volume > 0) {
            mainCtx.strokeStyle = "blue";
            mainCtx.lineWidth = hex.river_volume > 5 ? 3 : 1;
            mainCtx.beginPath();
            mainCtx.moveTo(px, py);
            // Draw a line towards an arbitrary neighbor for visual
            mainCtx.lineTo(px + hexSize*0.5, py + hexSize*0.5);
            mainCtx.stroke();
            mainCtx.lineWidth = 1;
        }

        if (hex.chaos_domain) {
            mainCtx.fillStyle = "rgba(255, 0, 0, 0.4)";
            mainCtx.fill();
            mainCtx.fillStyle = "white";
            mainCtx.font = `${hexSize/2}px Arial`;
            mainCtx.fillText("🔥", px - hexSize/4, py + hexSize/4);
        }
        
        // Icons
        let text = "";
        let biome = hex.pack_geo & 0xF;
        if (biome === 1 || biome === 0) text = "🌲";
        if (biome === 6) text = "⛰️";
        if (biome === 7) text = "🌋";
        
        // Settlement
        if (settlementsByHex[hex.id]) text = "🏰";
        
        // Entities (Chaos, Storms, Prisons)
        if (entitiesByHex[hex.id]) {
            for (let e of entitiesByHex[hex.id]) {
                if (e.type === "Chaos Creature" || e.type === "Cult Monster") text = "🦑";
                if (e.type === "Prison") text = "🏛️";
            }
        }
        
        let w_key = `${hex.q},${hex.r}`;
        if (weatherByHex[w_key]) {
            for (let w of weatherByHex[w_key]) {
                if (w.is_chaos) text = "🌀"; // Chaos Storm
                else if (w.type === "Hurricane" || w.type === "Tornado") text = "🌪️";
            }
        }
        
        if (text) {
            mainCtx.font = `${hexSize * (text === "🏛️" ? 1.5 : 0.8)}px Arial`;
            mainCtx.textAlign = "center";
            mainCtx.textBaseline = "middle";
            mainCtx.fillText(text, px, py);
        }
    }
    
    // Draw Leylines (not culled by screen bounds)
    for (let e of mapData.entities) {
        if (e.type === "Prison") {
            // Find global hex
            let hex = mapData.hexes.find(h => h.id === e.global_hex_id);
            if (!hex) continue;
            
            let curr_q = hex.q;
            let curr_r = hex.r;
            
            mainCtx.beginPath();
            let startPx = offsetX + w3 * (curr_q + curr_r / 2);
            let startPy = offsetY - h32 * curr_r;
            mainCtx.moveTo(startPx, startPy);
            
            // Draw a straight smooth line to the center (0,0)
            let endPx = offsetX;
            let endPy = offsetY;
            mainCtx.lineTo(endPx, endPy);
            
            mainCtx.strokeStyle = "rgba(255, 0, 255, 0.5)"; // Glowing magenta leyline
            mainCtx.lineWidth = 4;
            mainCtx.lineJoin = "round";
            mainCtx.lineCap = "round";
            mainCtx.stroke();
            mainCtx.lineWidth = 1;
        }
    }
}

// --- Interaction ---

miniCanvas.addEventListener('mousedown', (e) => {
    const rect = miniCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const scaleX = miniCanvas.width / (maxPx - minPx || 1);
    const scaleY = miniCanvas.height / (maxPy - minPy || 1);
    const scale = Math.min(scaleX, scaleY) * 0.9;
    
    const ox = (miniCanvas.width - (maxPx - minPx) * scale) / 2;
    const oy = (miniCanvas.height - (maxPy - minPy) * scale) / 2;
    
    const clickPx = (x - ox) / scale + minPx;
    const clickPy = (y - oy) / scale + minPy;
    
    viewportX = clickPx * zoomLevel;
    viewportY = clickPy * zoomLevel;
    
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
    
    // Reverse flat-topped hex projection
    const hexSize = zoomLevel;
    const px = x - offsetX;
    const py = y - offsetY;
    
    const frac_r = py / (-1.5 * hexSize);
    const frac_q = px / (Math.sqrt(3) * hexSize) - frac_r / 2;
    const frac_s = -frac_q - frac_r;
    
    let rq = Math.round(frac_q);
    let rr = Math.round(frac_r);
    let rs = Math.round(frac_s);
    
    const q_diff = Math.abs(rq - frac_q);
    const r_diff = Math.abs(rr - frac_r);
    const s_diff = Math.abs(rs - frac_s);
    
    if (q_diff > r_diff && q_diff > s_diff) rq = -rr - rs;
    else if (r_diff > s_diff) rr = -rq - rs;
    
    const q = rq;
    const r = rr;
    
    if (isDouble) {
        document.getElementById('cluster-content').innerText = "Loading Micro-Cluster...";
        const res = await fetch(`/api/micro/${q}/${r}`);
        if (res.status === 404) {
            document.getElementById('cluster-content').innerText = "Hex not found in DB.";
            return;
        }
        const data = await res.json();
        renderCluster(data);
    } else {
        document.getElementById('hex-content').innerText = "Loading...";
        const res = await fetch(`/api/hex/${q}/${r}`);
        if (res.status === 404) {
            document.getElementById('hex-content').innerText = "Hex not found in DB.";
        } else {
            const data = await res.json();
            const p1 = data.pack_ecology & 255;
            const p2 = (data.pack_ecology >> 8) & 255;
            const p3 = (data.pack_ecology >> 16) & 255;
            
            let settlementHtml = "";
            if (data.settlement) {
                const s = data.settlement;
                let inv = {};
                try { inv = JSON.parse(s.inventory_json); } catch(e) {}
                let loadout = [];
                try { loadout = JSON.parse(s.magic_loadout); } catch(e) {}
                
                settlementHtml = `<hr style="border-color: rgba(255,255,255,0.1); margin: 15px 0;">
                <strong style="color: var(--accent); font-size: 1.1rem;">🏰 ${s.name} <small style="color: var(--text-muted);">(${s.faction_name || "Independent"})</small></strong><br>
                <div class="stats-grid">
                    <div class="stat-box"><strong>Population</strong>${s.population.toFixed(0)}</div>
                    <div class="stat-box"><strong>Wealth</strong>${s.wealth.toFixed(0)}</div>
                    <div class="stat-box"><strong>Security</strong>${s.security_points.toFixed(0)}</div>
                </div>`;
                
                if (inv.Survival || inv.Building) {
                    settlementHtml += `<div style="margin-top: 15px; font-size: 0.85rem; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px;">
                        <strong style="color: var(--text-main); margin-bottom: 5px; display: block;">📦 Local Inventory</strong>`;
                    if (inv.Survival) settlementHtml += `<span style="color:var(--text-muted)">Food:</span> ${inv.Survival.Food?.toFixed(0) || 0} | <span style="color:var(--text-muted)">Water:</span> ${inv.Survival.Water?.toFixed(0) || 0}<br>`;
                    if (inv.Building) settlementHtml += `<span style="color:var(--text-muted)">Wood:</span> ${inv.Building.Wood?.toFixed(0) || 0} | <span style="color:var(--text-muted)">Stone:</span> ${inv.Building.Stone?.toFixed(0) || 0}<br>`;
                    settlementHtml += `</div>`;
                }
                
                if (s.hidden_cultists > 0) {
                    settlementHtml += `<div class="badge badge-danger" style="margin-top: 10px;">🩸 Hidden Cultists: ${s.hidden_cultists}</div><br>`;
                }
                if (loadout.length > 0) {
                    settlementHtml += `<div class="badge badge-magic" style="margin-top: 10px;">✨ Domains: ${loadout.join(", ")}</div>`;
                }
            }

            document.getElementById('hex-content').innerHTML = `
            <div class="fade-in">
                <strong>Coordinates:</strong> q=${data.q}, r=${data.r}<br>
                <strong>Biome:</strong> ${BIOME_NAMES[data.biome] || "Unknown"} (${data.biome})<br>
                <strong>Elevation:</strong> ${(data.elevation * 100).toFixed(0)}m<br>
                <strong>Ecology:</strong> Flora: ${p1}, Prey: ${p2}, Predators: ${p3}<br>
                <strong>River Vol:</strong> ${data.river_volume.toFixed(1)} ${data.is_lake ? " (Lake 💧)" : ""}<br>
                ${data.chaos_domain ? `<div class="badge badge-danger" style="margin-top:10px;">🔥 Chaos Domain: ${data.chaos_domain}</div><br>` : ""}
                ${settlementHtml}
            </div>
            `;
        }
    }
}

function renderCluster(data) {
    if (data.error) {
        document.getElementById('cluster-content').innerText = data.error;
        return;
    }
    currentMicroData = data;
    
    // Draw micro canvas
    microCtx.clearRect(0, 0, microCanvas.width, microCanvas.height);
    const mSize = 12; // 12 pixels per micro hex
    const mOffsetX = microCanvas.width / 2;
    const mOffsetY = microCanvas.height / 2;
    
    // Hex rendering helpers for axial
    function drawHex(ctx, x, y, size, color) {
        ctx.fillStyle = color;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = Math.PI / 3 * i + Math.PI / 6;
            const px = x + size * Math.cos(angle);
            const py = y + size * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.2)";
        ctx.stroke();
    }
    
    const w3 = Math.sqrt(3) * mSize;
    const h32 = 1.5 * mSize;
    
    let overlay = document.getElementById('overlaySelect') ? document.getElementById('overlaySelect').value : "biome";
    
    for (let hx of data.micro_hexes) {
        const px = mOffsetX + w3 * (hx.q + hx.r / 2);
        const py = mOffsetY - h32 * hx.r; // negative r
        
        let color = BIOME_COLORS[hx.biome_id] || "#333";
        if (overlay === "ecology_p1") color = `rgb(0, ${hx.p1}, 0)`;
        else if (overlay === "ecology_p2") color = `rgb(${hx.p2}, ${Math.floor(hx.p2*0.6)}, 0)`;
        else if (overlay === "ecology_p3") color = `rgb(${hx.p3}, 0, 0)`;
        
        drawHex(microCtx, px, py, mSize, color);
    }
    
    // Draw markers
    for (let s of data.settlements) {
        const px = mOffsetX + w3 * (s.micro_q + s.micro_r / 2);
        const py = mOffsetY - h32 * s.micro_r;
        microCtx.font = "24px Arial";
        microCtx.textAlign = "center";
        microCtx.textBaseline = "middle";
        microCtx.fillText("🏰", px, py);
        microCtx.font = "bold 10px Arial";
        microCtx.fillStyle = "white";
        microCtx.strokeStyle = "black";
        microCtx.lineWidth = 2;
        microCtx.strokeText(s.name, px, py + 16);
        microCtx.fillText(s.name, px, py + 16);
    }
    
    for (let e of data.entities) {
        const px = mOffsetX + w3 * (e.micro_q + e.micro_r / 2);
        const py = mOffsetY - h32 * e.micro_r;
        microCtx.font = "12px Arial";
        microCtx.textAlign = "center";
        microCtx.textBaseline = "middle";
        microCtx.fillText(e.type === "Hurricane" ? "🌪️" : "🦑", px, py);
    }
    
    let html = `<div class="fade-in">
        <strong>Global Center:</strong> q=${data.global_q}, r=${data.global_r}<br>
        <div class="badge badge-success" style="margin: 10px 0;">🌐 Active Trade Routes: ${data.active_trade_routes || 0}</div><br>
        <strong>Settlements in Cluster:</strong><br>`;
    for (let s of data.settlements) {
        html += `<small style="display:block; padding: 4px; background: rgba(255,255,255,0.05); margin-bottom: 4px; border-radius: 4px;">🏰 <strong>${s.name}</strong> (Pop: ${s.population.toFixed(0)} | Sec: ${s.security_points.toFixed(0)})</small>`;
    }
    if (data.settlements.length === 0) html += `<small style="color: var(--text-muted);"><em>No settlements</em></small><br>`;
    
    html += `<strong style="margin-top: 10px; display:block;">Local Entities:</strong>`;
    for (let e of data.entities) {
        html += `<small style="display:block; color: var(--danger);">👾 ${e.type} ${e.alignment ? '('+e.alignment+')' : ''}</small>`;
    }
    if (data.entities.length === 0) html += `<small style="color: var(--text-muted);"><em>None</em></small>`;
    html += `</div>`;
    
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

// --- Micro Canvas Tooltip ---
const tooltip = document.createElement('div');
tooltip.style.position = 'absolute';
tooltip.style.background = 'rgba(0,0,0,0.85)';
tooltip.style.color = '#fff';
tooltip.style.padding = '8px';
tooltip.style.borderRadius = '4px';
tooltip.style.pointerEvents = 'none';
tooltip.style.fontSize = '0.8rem';
tooltip.style.zIndex = '1000';
tooltip.style.display = 'none';
document.body.appendChild(tooltip);

microCanvas.addEventListener('mousemove', (e) => {
    if (!currentMicroData) return;
    
    const rect = microCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const mSize = 12;
    const mOffsetX = microCanvas.width / 2;
    const mOffsetY = microCanvas.height / 2;
    const w3 = Math.sqrt(3) * mSize;
    const h32 = 1.5 * mSize;
    
    const px = x - mOffsetX;
    const py = y - mOffsetY;
    
    const frac_r = py / (-h32);
    const frac_q = px / w3 - frac_r / 2;
    const frac_s = -frac_q - frac_r;
    
    let rq = Math.round(frac_q);
    let rr = Math.round(frac_r);
    let rs = Math.round(frac_s);
    
    const q_diff = Math.abs(rq - frac_q);
    const r_diff = Math.abs(rr - frac_r);
    const s_diff = Math.abs(rs - frac_s);
    if (q_diff > r_diff && q_diff > s_diff) rq = -rr - rs;
    else if (r_diff > s_diff) rr = -rq - rs;
    
    const hx = currentMicroData.micro_hexes.find(h => h.q === rq && h.r === rr);
    if (hx) {
        tooltip.style.display = 'block';
        tooltip.style.left = e.pageX + 10 + 'px';
        tooltip.style.top = e.pageY + 10 + 'px';
        
        const biomeName = BIOME_NAMES[hx.biome_id] || "Unknown";
        const elev = (hx.elevation * 100).toFixed(0);
        
        tooltip.innerHTML = `<strong style="color:var(--accent)">${biomeName}</strong><br>
            Elev: ${elev}m<br>
            Flora: ${hx.p1}<br>
            Prey: ${hx.p2}<br>
            Predators: ${hx.p3}`;
    } else {
        tooltip.style.display = 'none';
    }
});
microCanvas.addEventListener('mouseout', () => tooltip.style.display = 'none');
