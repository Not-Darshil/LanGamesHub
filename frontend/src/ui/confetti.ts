/** A short full-screen confetti burst on a throwaway canvas. Skipped for reduced motion. */
const COLORS = ["#8b5cf6", "#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#f472b6"];

export function fireConfetti(duration = 2600): void {
  if (typeof window === "undefined") return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  Object.assign(canvas.style, { position: "fixed", inset: "0", width: "100%", height: "100%", pointerEvents: "none", zIndex: "2000" });
  document.body.appendChild(canvas);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = (canvas.width = window.innerWidth * dpr);
  const height = (canvas.height = window.innerHeight * dpr);
  const g = canvas.getContext("2d");
  if (!g) { canvas.remove(); return; }
  const pieces = Array.from({ length: 180 }, (_, i) => {
    const fromLeft = i % 2 === 0;
    return {
      x: fromLeft ? 0 : width, y: height * 0.75,
      vx: (fromLeft ? 1 : -1) * (8 + Math.random() * 14) * dpr,
      vy: -(14 + Math.random() * 16) * dpr,
      w: (6 + Math.random() * 6) * dpr, h: (8 + Math.random() * 10) * dpr,
      rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
      color: COLORS[i % COLORS.length]!, shape: Math.random() < 0.3 ? 1 : 0,
    };
  });
  const start = performance.now();
  const frame = (now: number) => {
    const t = now - start;
    g.clearRect(0, 0, width, height);
    for (const p of pieces) {
      p.vy += 0.45 * dpr;
      p.vx *= 0.985;
      p.vy *= 0.985;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vr;
      g.save();
      g.globalAlpha = Math.max(0, 1 - t / duration);
      g.translate(p.x, p.y);
      g.rotate(p.rot);
      g.fillStyle = p.color;
      if (p.shape) { g.beginPath(); g.arc(0, 0, p.w / 2, 0, Math.PI * 2); g.fill(); }
      else g.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.rot * 2)));
      g.restore();
    }
    if (t < duration) requestAnimationFrame(frame);
    else canvas.remove();
  };
  requestAnimationFrame(frame);
}
