// Shatterlands VTT Canvas Adapter

const BIOME_COLORS = {
    0: "#FFFF00", // Jungle
    1: "#228B22", // Forest
    2: "#00FFFF", // Taiga
    3: "#DAA520", // Desert
    4: "#6B8E23", // Plains
    5: "#2F4F4F", // Tundra
    6: "#8B4513", // Mountain
    7: "#FF4500", // Volcano
    8: "#FFFAFA", // Arctic
    9: "#20B2AA", // Kelp Forest
    10: "#0000CD", // Coral Reef
    11: "#000080", // Arctic Ocean
    12: "#000033", // Abyssal Trench
    13: "#4B0082"  // Prison Wastes
};

class VTTCanvasAdapter {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');

        // Setup initial canvas size
        this.resize();
        window.addEventListener('resize', () => this.resize());

        // Hex math constants
        this.scale = 10; // Base scale for tactical tiles
        this.hexWidth = Math.sqrt(3) * this.scale;
        this.hexHeight = 2 * this.scale;
        this.xOffsetStep = this.hexWidth;
        this.yOffsetStep = 3/4 * this.hexHeight;

        this.offsetX = this.canvas.width / 2;
        this.offsetY = this.canvas.height / 2;

        this.currentPayload = null;
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.offsetX = this.canvas.width / 2;
        this.offsetY = this.canvas.height / 2;
        if (this.currentPayload) {
            this.renderPayload(this.currentPayload);
        }
    }

    renderPayload(payload) {
        this.currentPayload = payload;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Render base background
        this.ctx.fillStyle = payload.is_underwater ? '#0a192f' : '#1e1e1e';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // 1. Draw Grid (55-ring local grid math -> tactical tiles)
        this.drawTacticalGrid();

        // 2. Render Vertical Depth Markers
        this.renderDepthMarkers(payload);

        // 3. Render Chaos Storm Boundaries
        this.renderStormBoundaries(payload);
    }

    drawHex(x, y, scale, color, strokeColor = "rgba(0,0,0,0.2)") {
        this.ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            let angle_deg = 60 * i - 30;
            let angle_rad = Math.PI / 180 * angle_deg;
            let px = x + scale * Math.cos(angle_rad);
            let py = y + scale * Math.sin(angle_rad);
            if (i === 0) { this.ctx.moveTo(px, py); }
            else { this.ctx.lineTo(px, py); }
        }
        this.ctx.closePath();
        if (color) {
            this.ctx.fillStyle = color;
            this.ctx.fill();
        }
        if (strokeColor) {
            this.ctx.strokeStyle = strokeColor;
            this.ctx.stroke();
        }
    }

    drawTacticalGrid() {
        // Implementation for drawing the tactical 5-foot grid
        // 55 rings of local hexes -> tactical tiles
        const rings = 55; // Render a limited number of rings for performance/viewport

        // Loop through axial coordinates to draw the grid
        for (let q = -rings; q <= rings; q++) {
            let r1 = Math.max(-rings, -q - rings);
            let r2 = Math.min(rings, -q + rings);
            for (let r = r1; r <= r2; r++) {
                let px = this.offsetX + this.hexWidth * (q + r/2);
                let py = this.offsetY + this.yOffsetStep * r;

                // Only draw if within viewport to save performance
                if (px >= -this.hexWidth && px <= this.canvas.width + this.hexWidth &&
                    py >= -this.hexHeight && py <= this.canvas.height + this.hexHeight) {

                    this.drawHex(px, py, this.scale, "rgba(255,255,255,0.05)");
                }
            }
        }
    }

    renderDepthMarkers(payload) {
        // Implementation for depth markers (Surface vs Sub-surface/Abyssal)
        if (payload.is_underwater) {
            this.ctx.fillStyle = "rgba(0, 100, 255, 0.2)";
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

            this.ctx.fillStyle = "cyan";
            this.ctx.font = "20px Arial";
            this.ctx.fillText(`Depth Layer: ${payload.depth_layer}`, 20, 100);

            if (payload.ocean_attributes) {
                this.ctx.font = "16px Arial";
                this.ctx.fillText(`Biome: ${payload.ocean_attributes.underwater_biome}`, 20, 125);
                this.ctx.fillText(`Current Index: ${payload.ocean_attributes.active_current_index}`, 20, 145);
            }
        } else {
            this.ctx.fillStyle = "lightgreen";
            this.ctx.font = "20px Arial";
            this.ctx.fillText(`Depth Layer: ${payload.depth_layer}`, 20, 100);
        }
    }

    renderStormBoundaries(payload) {
         // Implementation for active storms boundaries
         if (payload.active_storms && payload.active_storms.length > 0) {
            payload.active_storms.forEach((storm, index) => {
                if (storm.is_chaos) {
                    const radius = storm.energy / 10; // Simplified radius calculation
                    const centerX = this.offsetX; // Assume storm is centered for this localized payload
                    const centerY = this.offsetY;

                    // Draw active storm radius
                    this.ctx.beginPath();
                    this.ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);

                    // Style based on domain
                    if (storm.chaos_domain === "Void") {
                        this.ctx.fillStyle = "rgba(128, 0, 128, 0.3)";
                        this.ctx.strokeStyle = "purple";
                    } else {
                        this.ctx.fillStyle = "rgba(255, 0, 0, 0.3)";
                        this.ctx.strokeStyle = "red";
                    }

                    this.ctx.fill();
                    this.ctx.lineWidth = 3;
                    this.ctx.stroke();
                    this.ctx.lineWidth = 1;

                    // Draw storm label
                    this.ctx.fillStyle = "white";
                    this.ctx.font = "bold 14px Arial";
                    this.ctx.textAlign = "center";
                    this.ctx.fillText(`${storm.chaos_domain} Storm Boundary`, centerX, centerY - radius - 10);
                    this.ctx.textAlign = "left"; // reset
                }
            });
         }
    }
}
