function renderMap() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    mapData.hexes.forEach(hex => {
        const { x, y } = hexToPixel(hex.q, hex.r);
        if (x < -20 || x > canvas.width + 20 || y < -20 || y > canvas.height + 20) return;
        
        const biomeId = hex.pack_geo & 0xF;
        let terrainHeight = (hex.pack_geo >> 4) & 0xF;
        
        // Identify marine/abyssal coordinates naturally by biome mapping IDs
        let isMarine = [0, 1, 2, 3, 4, 9, 10, 11, 12].includes(biomeId);
        let color = '#202024';
        
        if (viewSubSurface) {
            if (isMarine) {
                // UNIFIED NATIVE ELEVATION SCALING
                // No more inversion trick formulas. The deeper the terrain feature is stored,
                // the more vibrant and intense the neon purple matrix visualization paints.
                let intensity = Math.floor((terrainHeight / 15) * 155) + 100;
                color = `rgb(${intensity}, 30, ${intensity})`;
            } else {
                color = '#111112'; // Dim out continental landmasses cleanly
            }
        } else {
            // STANDARD CONFIGURATION SURFACE VIEW
            if (isMarine) {
                color = `rgb(25, 60, ${120 + terrainHeight * 8})`; // Sea gradient ramps
            } else {
                color = `rgb(45, ${110 + terrainHeight * 9}, 45)`; // Continent elevation ramps
            }
        }
        
        let stroke = '#29292e';
        if (hex.chaos_domain > 0) stroke = '#9871f5'; // Highlight chaos anomalies
        
        drawHexagon(x, y, color, stroke);
    });
}

const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');
let mapData = { hexes: [], settlements: [], entities: [], weather: [] };
let viewSubSurface = false;
let zoom = 1.0;
const baseHexSize = 10;
let offsetX = canvas.width / 2;
let offsetY = canvas.height / 2;

function hexToPixel(q, r) {
    const size = baseHexSize * zoom;
    const x = size * Math.sqrt(3) * (q + r / 2);
    const y = size * 3/2 * r;
    return { x: x + offsetX, y: y + offsetY };
}

function pixelToHex(x, y) {
    const size = baseHexSize * zoom;
    const ptX = x - offsetX;
    const ptY = y - offsetY;
    const q = (Math.sqrt(3)/3 * ptX - 1/3 * ptY) / size;
    const r = (2/3 * ptY) / size;
    return { q: Math.round(q), r: Math.round(r) };
}

function drawHexagon(x, y, color, stroke) {
    const size = baseHexSize * zoom;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 180) * (60 * i - 30);
        const px = x + size * Math.cos(angle);
        const py = y + size * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.stroke();
}

// Keep track of the active cluster data globally in the frontend for mouse-hover lookups
let activeClusterHexes = [];

function clearMicroCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawHexOnCanvas(micro_q, micro_r, color) {
    const { x, y } = hexToPixel(micro_q, micro_r);
    drawHexagon(x, y, color, '#111');
}

function pixelToHexAxial(x, y) {
    const coords = pixelToHex(x, y);
    return [coords.q, coords.r];
}

async function updateDashboardWithRealData(globalQ, globalR) {
    document.getElementById("hud-global-coords").innerText = `Global Hex: (Q: ${globalQ}, R: ${globalR})`;

    try {
        const response = await fetch(`/api/cluster/${globalQ}/${globalR}`);
        if (!response.ok) throw new Error("Network response failed.");
        const data = await response.json();

        activeClusterHexes = data.hexes; // Save the raw array of 91 nodes

        let totalP1 = 0, totalP2 = 0, totalP3 = 0, totalRes = 0;

        // Clear background canvas and map out the nested ring array
        clearMicroCanvas();

        activeClusterHexes.forEach(subHex => {
            // Aggregate totals for the top-level averages
            totalP1 += subHex.ecology.plants;
            totalP2 += subHex.ecology.prey;
            totalP3 += subHex.ecology.predators;
            totalRes += subHex.ecology.resources;

            // Run your existing visual tile rendering step based on the real types
            let tileColor = `rgb(30, ${Math.min(200, 40 + subHex.ecology.plants)}, 30)`;
            if (subHex.settlement === "Town Center") tileColor = "#d4af37";
            else if (subHex.infrastructure === "Farm Field") tileColor = "#b45309";
            else if (subHex.infrastructure === "Outpost Wall") tileColor = "#64748b";
            else if (subHex.infrastructure === "Resource Mine") tileColor = "#0284c7";

            drawHexOnCanvas(subHex.micro_q, subHex.micro_r, tileColor);
        });

        // Calculate and push cluster averages straight into the top display slots
        const totalNodes = activeClusterHexes.length || 1;
        document.getElementById("hud-avg-p1").innerText = Math.round(totalP1 / totalNodes);
        document.getElementById("hud-avg-p2").innerText = Math.round(totalP2 / totalNodes);
        document.getElementById("hud-avg-p3").innerText = Math.round(totalP3 / totalNodes);
        document.getElementById("hud-avg-res").innerText = Math.round(totalRes / totalNodes);

    } catch (err) {
        console.error("Failed to update numerical HUD:", err);
    }
}

let isDragging = false;
let lastX = 0, lastY = 0;

canvas.addEventListener('mousedown', e => {
    isDragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
});

canvas.addEventListener('click', e => {
    if (isDragging && (Math.abs(e.clientX - lastX) > 5 || Math.abs(e.clientY - lastY) > 5)) return;
    const rect = canvas.getBoundingClientRect();
    const hexCoords = pixelToHex(e.clientX - rect.left, e.clientY - rect.top);
    updateDashboardWithRealData(hexCoords.q, hexCoords.r);
});

// 3. HOVER INTERACTION OVERLAY HOOK
// Connect this tool directly to your existing canvas 'mousemove' event listener!
function handleCanvasMouseMove(mouseEvent) {
    // Convert your mouse screen coordinates to hex axial coordinates (micro_q, micro_r)
    const rect = canvas.getBoundingClientRect();
    const [mq, mr] = pixelToHexAxial(mouseEvent.clientX - rect.left, mouseEvent.clientY - rect.top);

    // Scan our active 91-hex array for a coordinate match
    const targetNode = activeClusterHexes.find(h => h.micro_q === mq && h.micro_r === mr);
    const detailPanel = document.getElementById("hud-node-details");

    if (targetNode) {
        const eco = targetNode.ecology;
        const structureLabel = targetNode.settlement || targetNode.infrastructure || "Untouched Wilderness";

        detailPanel.innerHTML = `
            <strong>Coord:</strong> (${mq}, ${mr})<br>
            <strong>Type:</strong> <span style="color: #38bdf8;">${structureLabel}</span><br>
            <span style="color: #4ade80;">P1: ${eco.plants}</span> |
            <span style="color: #fbbf24;">P2: ${eco.prey}</span> |
            <span style="color: #f87171;">P3: ${eco.predators}</span>
        `;
    } else {
        detailPanel.innerText = "Hover over a nested 18.5 km tile to inspect local numbers...";
    }
}

canvas.addEventListener('mousemove', e => {
    if (isDragging) {
        offsetX += e.clientX - lastX;
        offsetY += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        renderMap();
    } else {
        // Hover inspect
        const rect = canvas.getBoundingClientRect();
        const hexCoords = pixelToHex(e.clientX - rect.left, e.clientY - rect.top);
        const hex = mapData.hexes.find(h => h.q === hexCoords.q && h.r === hexCoords.r);
        if (hex) {
            const biome = hex.pack_geo & 0xF;
            const elevation = (hex.pack_geo >> 4) & 0xF;
            document.getElementById('inspector-output').innerHTML = `
                <strong>Coordinates:</strong> q=${hex.q}, r=${hex.r}<br>
                <strong>Biome ID:</strong> ${biome}<br>
                <strong>Elevation:</strong> ${elevation}<br>
                <strong>Ecology Pack:</strong> ${hex.pack_ecology}<br>
            `;
        }
        // Handle micro cluster HUD overlay
        handleCanvasMouseMove(e);
    }
});

canvas.addEventListener('mouseup', () => isDragging = false);
canvas.addEventListener('mouseleave', () => isDragging = false);
canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = zoom * zoomFactor;
    if (newZoom < 0.1 || newZoom > 10) return;

    // Zoom towards mouse
    offsetX = mouseX - (mouseX - offsetX) * zoomFactor;
    offsetY = mouseY - (mouseY - offsetY) * zoomFactor;
    zoom = newZoom;

    renderMap();
});

document.getElementById('btn-subsurface').addEventListener('click', () => {
    viewSubSurface = !viewSubSurface;
    renderMap();
});

document.getElementById('btn-tick').addEventListener('click', async () => {
    await fetch('/api/tick', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ticks: 1}) });
    await fetchState();
});

async function fetchState() {
    try {
        const [mapRes, statusRes, logsRes] = await Promise.all([
            fetch('/api/map'),
            fetch('/api/status'),
            fetch('/api/logs')
        ]);

        mapData = await mapRes.json();
        const status = await statusRes.json();
        const logs = await logsRes.json();

        document.getElementById('sim-time').innerText = `Tick: ${status.tick} | Day: ${status.day} | Year: ${status.year} | Season: ${status.season}`;
        document.getElementById('global-pop').innerText = `Population: ${status.global_population}`;

        const logStream = document.getElementById('log-stream');
        logStream.innerHTML = '';
        logs.forEach(log => {
            const el = document.createElement('div');
            el.className = `log-entry ${log.category}`;
            el.innerText = `[Tick ${log.tick}] ${log.category}: ${log.message}`;
            logStream.appendChild(el);
        });

        renderMap();
    } catch (e) {
        console.error("Failed to fetch state:", e);
    }
}

// Initial fetch
fetchState();
setInterval(fetchState, 5000);
