import { useEffect, useRef } from 'react';

/**
 * NeuralBackground — full-screen canvas AI neural network.
 * Features: hub nodes, data packets with motion trails, layered glow.
 * Respects prefers-reduced-motion and downscales on mobile.
 */
export default function NeuralBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isMobile = window.innerWidth < 768;

    const NODE_COUNT  = prefersReduced ? 15 : isMobile ? 38 : 110;
    const HUB_COUNT   = prefersReduced ? 0  : isMobile ? 2  : 6;
    const MAX_DIST    = isMobile ? 100 : 165;
    const SPEED       = prefersReduced ? 0  : isMobile ? 0.18 : 0.28;
    const PKT_COUNT   = prefersReduced ? 0  : isMobile ? 4   : 14;

    let width  = (canvas.width  = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const mkNode = (isHub) => ({
      x: isHub ? width  * (0.12 + Math.random() * 0.76) : Math.random() * width,
      y: isHub ? height * (0.12 + Math.random() * 0.76) : Math.random() * height,
      vx: (Math.random() - 0.5) * SPEED * (isHub ? 0.45 : 1),
      vy: (Math.random() - 0.5) * SPEED * (isHub ? 0.45 : 1),
      radius: isHub ? 3.5 + Math.random() * 2.5 : 1.2 + Math.random() * 1.8,
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: isHub ? 0.006 + Math.random() * 0.008 : 0.012 + Math.random() * 0.018,
      isHub,
    });

    const nodes = [
      ...Array.from({ length: NODE_COUNT }, () => mkNode(false)),
      ...Array.from({ length: HUB_COUNT  }, () => mkNode(true)),
    ];

    const packets = [];

    const spawnPacket = () => {
      for (let tries = 0; tries < 25; tries++) {
        const i = Math.floor(Math.random() * nodes.length);
        const j = Math.floor(Math.random() * nodes.length);
        if (i === j) continue;
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        if (Math.sqrt(dx * dx + dy * dy) < MAX_DIST) {
          packets.push({ fi: i, ti: j, t: 0, speed: 0.004 + Math.random() * 0.008, cyan: Math.random() > 0.5 });
          return;
        }
      }
    };

    for (let p = 0; p < PKT_COUNT; p++) spawnPacket();

    let animFrame;

    function draw() {
      ctx.clearRect(0, 0, width, height);

      // --- Connection lines ---
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < MAX_DIST) {
            const ratio = 1 - dist / MAX_DIST;
            const isHubEdge = nodes[i].isHub || nodes[j].isHub;
            const alpha = ratio * (isHubEdge ? 0.38 : 0.16);
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(58,160,255,${alpha})`;
            ctx.lineWidth = isHubEdge ? 0.8 : 0.5;
            ctx.stroke();
          }
        }
      }

      // --- Data packets ---
      for (let p = packets.length - 1; p >= 0; p--) {
        const pkt = packets[p];
        pkt.t += pkt.speed;
        if (pkt.t >= 1) { packets.splice(p, 1); spawnPacket(); continue; }

        const from = nodes[pkt.fi];
        const to   = nodes[pkt.ti];
        const edgeDx = from.x - to.x;
        const edgeDy = from.y - to.y;
        if (Math.sqrt(edgeDx * edgeDx + edgeDy * edgeDy) >= MAX_DIST) {
          packets.splice(p, 1); spawnPacket(); continue;
        }

        const px = from.x + (to.x - from.x) * pkt.t;
        const py = from.y + (to.y - from.y) * pkt.t;

        // motion trail
        const trailT = Math.max(0, pkt.t - 0.12);
        const tx = from.x + (to.x - from.x) * trailT;
        const ty = from.y + (to.y - from.y) * trailT;
        const tg = ctx.createLinearGradient(tx, ty, px, py);
        tg.addColorStop(0, 'rgba(77,184,255,0)');
        tg.addColorStop(1, pkt.cyan ? 'rgba(0,229,255,0.7)' : 'rgba(77,184,255,0.7)');
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(px, py);
        ctx.strokeStyle = tg;
        ctx.lineWidth = 1.4;
        ctx.stroke();

        // glow halo
        const pg = ctx.createRadialGradient(px, py, 0, px, py, 7);
        pg.addColorStop(0, pkt.cyan ? 'rgba(0,229,255,0.85)' : 'rgba(77,184,255,0.85)');
        pg.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.beginPath();
        ctx.arc(px, py, 7, 0, Math.PI * 2);
        ctx.fillStyle = pg;
        ctx.fill();

        // bright core
        ctx.beginPath();
        ctx.arc(px, py, 1.6, 0, Math.PI * 2);
        ctx.fillStyle = pkt.cyan ? '#00e5ff' : '#4db8ff';
        ctx.fill();
      }

      // --- Nodes ---
      for (const nd of nodes) {
        nd.x += nd.vx; nd.y += nd.vy;
        nd.pulse += nd.pulseSpeed;
        if (nd.x < 0) nd.x = width;  if (nd.x > width)  nd.x = 0;
        if (nd.y < 0) nd.y = height; if (nd.y > height) nd.y = 0;

        const ps  = 1 + Math.sin(nd.pulse) * 0.3;
        const r   = nd.radius * ps;

        if (nd.isHub) {
          // Triple-layer hub glow
          const g3 = ctx.createRadialGradient(nd.x, nd.y, 0, nd.x, nd.y, r * 12);
          g3.addColorStop(0, 'rgba(0,229,255,0.18)'); g3.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.beginPath(); ctx.arc(nd.x, nd.y, r * 12, 0, Math.PI * 2); ctx.fillStyle = g3; ctx.fill();

          const g2 = ctx.createRadialGradient(nd.x, nd.y, 0, nd.x, nd.y, r * 6);
          g2.addColorStop(0, 'rgba(0,229,255,0.45)'); g2.addColorStop(1, 'rgba(58,160,255,0)');
          ctx.beginPath(); ctx.arc(nd.x, nd.y, r * 6, 0, Math.PI * 2); ctx.fillStyle = g2; ctx.fill();

          ctx.beginPath(); ctx.arc(nd.x, nd.y, r, 0, Math.PI * 2); ctx.fillStyle = '#00e5ff'; ctx.fill();
        } else {
          const g = ctx.createRadialGradient(nd.x, nd.y, 0, nd.x, nd.y, r * 6);
          g.addColorStop(0, 'rgba(58,160,255,0.32)'); g.addColorStop(1, 'rgba(58,160,255,0)');
          ctx.beginPath(); ctx.arc(nd.x, nd.y, r * 6, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();

          ctx.beginPath(); ctx.arc(nd.x, nd.y, r, 0, Math.PI * 2); ctx.fillStyle = '#3aa0ff'; ctx.fill();
        }
      }

      animFrame = requestAnimationFrame(draw);
    }

    draw();

    const handleResize = () => {
      width  = canvas.width  = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animFrame);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed', inset: 0,
        width: '100%', height: '100%',
        zIndex: 0,
        background: 'radial-gradient(ellipse 120% 80% at 50% 0%, #040c1e 0%, #020409 55%, #010206 100%)',
        pointerEvents: 'none',
      }}
      aria-hidden="true"
    />
  );
}
