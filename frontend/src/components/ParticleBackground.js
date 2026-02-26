import { useEffect, useRef } from 'react';

/**
 * ParticleBackground
 * Modern 3D-ish particle field with depth perspective and subtle connections.
 * Used on Landing, Login, and Register pages.
 * Lightweight canvas-based animation — no external dependencies.
 */

function randomBetween(a, b) {
  return a + Math.random() * (b - a);
}

// Subtle dark-compatible palette with depth
const COLORS = [
  'rgba(96, 165, 250, ALPHA)',   // blue
  'rgba(52, 211, 153, ALPHA)',   // teal
  'rgba(167, 139, 250, ALPHA)',  // purple
  'rgba(251, 191, 36, ALPHA)',   // gold (accent)
];

export default function ParticleBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const PARTICLE_COUNT = 80;
    const CONNECTION_DIST = 120; // max distance to draw a connection line

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // Each particle has a z-depth (0–1) to simulate 3D perspective
    const particles = Array.from({ length: PARTICLE_COUNT }, () => {
      const z = randomBetween(0.1, 1.0); // depth: 1 = front, 0.1 = far
      const colorTemplate = COLORS[Math.floor(Math.random() * COLORS.length)];
      return {
        x: randomBetween(0, canvas.width),
        y: randomBetween(0, canvas.height),
        z,
        r: randomBetween(1.0, 2.8) * z,   // larger = closer
        vx: randomBetween(-0.3, 0.3) * z, // faster = closer
        vy: randomBetween(-0.3, 0.3) * z,
        color: colorTemplate,
        alpha: randomBetween(0.15, 0.55) * z,
      };
    });

    let animId;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw connection lines between nearby particles (same z-layer ± 0.3)
      ctx.lineWidth = 0.5;
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < CONNECTION_DIST && Math.abs(a.z - b.z) < 0.35) {
            const lineAlpha = (1 - dist / CONNECTION_DIST) * 0.08 * Math.min(a.z, b.z);
            ctx.strokeStyle = `rgba(96,165,250,${lineAlpha})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      // Draw particles with glow
      for (const p of particles) {
        // Update position
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -10) p.x = canvas.width + 10;
        if (p.x > canvas.width + 10) p.x = -10;
        if (p.y < -10) p.y = canvas.height + 10;
        if (p.y > canvas.height + 10) p.y = -10;

        const colorStr = p.color.replace('ALPHA', String(p.alpha));

        // Soft glow (larger, transparent)
        const glowR = p.r * 3.5;
        const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR);
        gradient.addColorStop(0, p.color.replace('ALPHA', String(p.alpha * 0.4)));
        gradient.addColorStop(1, p.color.replace('ALPHA', '0'));
        ctx.beginPath();
        ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Core dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = colorStr;
        ctx.fill();
      }

      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  );
}
