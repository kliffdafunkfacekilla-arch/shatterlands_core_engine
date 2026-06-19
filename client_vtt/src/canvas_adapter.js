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