import { useEffect, useRef } from 'react';

/**
 * NeuralBackground — full-screen canvas neural network animation.
 * Uses requestAnimationFrame for smooth 60fps rendering.
 * Automatically reduces complexity on mobile and for prefers-reduced-motion.
 */
export default function NeuralBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isMobile = window.innerWidth < 768;

    const NODE_COUNT = prefersReduced ? 20 : isMobile ? 30 : 75;
    const MAX_DIST = isMobile ? 90 : 150;
    const SPEED = prefersReduced ? 0 : isMobile ? 0.2 : 0.35;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const nodes = Array.from({ length: NODE_COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * SPEED,
      vy: (Math.random() - 0.5) * SPEED,
      radius: Math.random() * 2 + 1.5,
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: 0.008 + Math.random() * 0.014,
    }));

    let animFrame;

    function draw() {
      ctx.clearRect(0, 0, width, height);

      // Draw connection lines between nearby nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < MAX_DIST) {
            const alpha = (1 - dist / MAX_DIST) * 0.22;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(58,160,255,${alpha})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
      }

      // Update positions and draw nodes
      for (const node of nodes) {
        node.x += node.vx;
        node.y += node.vy;
        node.pulse += node.pulseSpeed;

        // Wrap around edges
        if (node.x < 0) node.x = width;
        if (node.x > width) node.x = 0;
        if (node.y < 0) node.y = height;
        if (node.y > height) node.y = 0;

        const pulseScale = 1 + Math.sin(node.pulse) * 0.25;
        const r = node.radius * pulseScale;
        const glowR = r * 5;

        // Outer glow
        const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowR);
        grad.addColorStop(0, 'rgba(0,229,255,0.4)');
        grad.addColorStop(1, 'rgba(0,229,255,0)');
        ctx.beginPath();
        ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Core node
        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
        ctx.fillStyle = '#3aa0ff';
        ctx.fill();
      }

      animFrame = requestAnimationFrame(draw);
    }

    draw();

    const handleResize = () => {
      width = canvas.width = window.innerWidth;
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
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        background: '#05070d',
        pointerEvents: 'none',
      }}
      aria-hidden="true"
    />
  );
}
