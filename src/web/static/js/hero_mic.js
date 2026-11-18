/* ---------- Home hero mic: a small 3D mic on a stand, drawn on a canvas ----------
   The mic is a real 3D shape (tilted handle, ring and ball head on a vertical stand). Every frame its
   axis is turned around the stand and projected onto the screen, so it truly turns in depth (the head
   swings toward and away from the viewer) instead of a flat picture being squeezed.
   The stage light stays still, up and to the right: highlights and rim light are always on the right
   side, shadow on the left, and the head's shine moves as the head turns. Style follows the Landing
   mic photo: matte black body, metal mesh head, silver ring.
   The loop only runs while the mic is on screen (Home is active and the tab is visible). With
   "reduce motion" it draws one still frame. */

const W = 160, H = 420;                 // drawing units (the canvas is scaled to its CSS size)
const PIVOT = { x: 80, y: 172 };         // clip on top of the stand, where the mic turns
const TILT = 22 * Math.PI / 180;         // mic leans this far from vertical
const TURN_S = 9;                        // seconds for one full turn around the stand
const LIGHT = { x: 0.62, y: -0.55 };     // light direction on screen (up and to the right)

/* project a point on the mic axis (s units from the pivot) for turn angle th */
function axisAt(s, th, tilt) {
  const dx = Math.sin(tilt) * Math.cos(th), dy = -Math.cos(tilt), dz = Math.sin(tilt) * Math.sin(th);
  return { x: PIVOT.x + dx * s, y: PIVOT.y + dy * s, z: dz * s };
}

function drawStand(c) {
  // floor: warm pool of stage light, and the shadow falling left (away from the light)
  let g = c.createRadialGradient(92, 404, 0, 92, 404, 64);
  g.addColorStop(0, 'rgba(255,236,190,.30)'); g.addColorStop(.6, 'rgba(255,236,190,.08)'); g.addColorStop(1, 'rgba(255,236,190,0)');
  c.fillStyle = g; c.beginPath(); c.ellipse(92, 404, 64, 13, 0, 0, Math.PI * 2); c.fill();
  g = c.createRadialGradient(64, 405, 0, 64, 405, 44);
  g.addColorStop(0, 'rgba(0,0,0,.6)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.beginPath(); c.ellipse(64, 405, 44, 7, 0, 0, Math.PI * 2); c.fill();
  // round weighted base
  c.fillStyle = '#060709'; c.beginPath(); c.ellipse(80, 403, 38, 9, 0, 0, Math.PI * 2); c.fill();
  g = c.createRadialGradient(100, 394, 2, 84, 400, 46);
  g.addColorStop(0, '#7A6D58'); g.addColorStop(.3, '#2A2A2D'); g.addColorStop(1, '#08090B');
  c.fillStyle = g; c.beginPath(); c.ellipse(80, 400, 38, 9, 0, 0, Math.PI * 2); c.fill();
  c.strokeStyle = 'rgba(232,212,170,.55)'; c.lineWidth = 1.2;
  c.beginPath(); c.ellipse(80, 400, 37, 8.4, 0, -1.25, -0.05); c.stroke();
  // pole (two tubes and a joint collar), lit on the right
  const tube = (x, y, w, h) => {
    const t = c.createLinearGradient(x, 0, x + w, 0);
    t.addColorStop(0, '#050608'); t.addColorStop(.5, '#17181C'); t.addColorStop(.76, '#3A3530'); t.addColorStop(.88, '#C9B387'); t.addColorStop(1, '#1E1F23');
    c.fillStyle = t; c.fillRect(x, y, w, h);
  };
  tube(76, 250, 8, 148);
  tube(77.5, 178, 5, 66);
  const collar = (x, y, w, h) => {
    const t = c.createLinearGradient(x, 0, x + w, 0);
    t.addColorStop(0, '#0B0C0F'); t.addColorStop(.6, '#2B2B2E'); t.addColorStop(.85, '#9A8763'); t.addColorStop(1, '#18191C');
    c.fillStyle = t; c.beginPath(); c.roundRect(x, y, w, h, 3); c.fill();
  };
  collar(74, 238, 12, 16);
  c.fillStyle = '#1A1B1E'; c.beginPath(); c.roundRect(84, 243, 7, 4, 2); c.fill();   // tightening knob
  collar(74, 166, 12, 16);                                                             // clip block
}

/* a band across the mic axis (handle section or ring): quad from s0 to s1 with half widths w0, w1 */
function band(c, th, tilt, s0, s1, w0, w1, stops) {
  const a = axisAt(s0, th, tilt), b = axisAt(s1, th, tilt);
  let px = -(b.y - a.y), py = b.x - a.x; const len = Math.hypot(px, py) || 1; px /= len; py /= len;
  if (px < 0) { px = -px; py = -py; }    // p points to the screen right (the lit side)
  const g = c.createLinearGradient(a.x - px * w0, a.y - py * w0, a.x + px * w0, a.y + py * w0);
  stops.forEach(s => g.addColorStop(s[0], s[1]));
  c.fillStyle = g; c.beginPath();
  c.moveTo(a.x - px * w0, a.y - py * w0); c.lineTo(b.x - px * w1, b.y - py * w1);
  c.lineTo(b.x + px * w1, b.y + py * w1); c.lineTo(a.x + px * w0, a.y + py * w0); c.closePath(); c.fill();
  return { a, b, px, py };
}

const HANDLE = [[0, '#040507'], [.45, '#121317'], [.7, '#26262A'], [.86, '#8E7C5B'], [.93, '#E8D4A6'], [1, '#2A2A2E']];
const RING = [[0, '#1D1E21'], [.45, '#7A776F'], [.72, '#F7E8C6'], [.86, '#B7AE9C'], [1, '#3A3A3D']];

function drawMic(c, th, tilt) {
  // clip bracket the handle sits in
  band(c, th, tilt, -6, 14, 9, 10, [[0, '#08090C'], [.75, '#2A2A2E'], [.9, '#7D6D51'], [1, '#141518']]);
  // tapered matte handle and the silver ring
  band(c, th, tilt, 0, 96, 6, 12, HANDLE);
  band(c, th, tilt, 94, 108, 14, 14, RING);
  // ball head: a sphere, so its outline stays round; the shine follows the fixed light
  const h = axisAt(128, th, tilt), R = 25;
  const hx = h.x + LIGHT.x * R * .5, hy = h.y + LIGHT.y * R * .5;
  const g = c.createRadialGradient(hx, hy, 1, h.x, h.y, R * 1.05);
  g.addColorStop(0, '#FBEFD2'); g.addColorStop(.2, '#B1A68F'); g.addColorStop(.55, '#4A494E'); g.addColorStop(1, '#0F1013');
  c.save();
  c.beginPath(); c.arc(h.x, h.y, R, 0, Math.PI * 2); c.fillStyle = g; c.fill(); c.clip();
  // mesh: fine cross-hatch over the ball
  c.strokeStyle = 'rgba(8,9,12,.55)'; c.lineWidth = .8;
  for (let k = -2 * R; k <= 2 * R; k += 3.2) {
    c.beginPath(); c.moveTo(h.x + k - R, h.y - R); c.lineTo(h.x + k + R, h.y + R); c.stroke();
    c.beginPath(); c.moveTo(h.x + k + R, h.y - R); c.lineTo(h.x + k - R, h.y + R); c.stroke();
  }
  // seam around the head, at right angles to the axis: an ellipse that opens and closes as it turns
  const ax = axisAt(1, th, tilt), ux = ax.x - PIVOT.x, uy = ax.y - PIVOT.y, uz = ax.z;
  const ang = Math.atan2(uy, ux) + Math.PI / 2, open = Math.max(.08, Math.abs(uz) + Math.abs(Math.sin(tilt)) * .25);
  const sc = axisAt(122, th, tilt);
  c.strokeStyle = 'rgba(14,15,18,.75)'; c.lineWidth = 2.4;
  c.beginPath(); c.ellipse(sc.x, sc.y, R * .98, R * open, ang, 0, Math.PI * 2); c.stroke();
  c.strokeStyle = 'rgba(214,196,156,.55)'; c.lineWidth = .8;
  c.beginPath(); c.ellipse(sc.x, sc.y - .8, R * .98, R * open, ang, 0, Math.PI * 2); c.stroke();
  c.restore();
  // rim light on the right edge and a soft shine
  c.strokeStyle = 'rgba(255,241,210,.8)'; c.lineWidth = 2.2; c.lineCap = 'round';
  c.beginPath(); c.arc(h.x, h.y, R - 1.2, -1.15, 0.55); c.stroke();
  c.fillStyle = 'rgba(255,246,226,.5)';
  c.beginPath(); c.ellipse(hx, hy, 6.5, 3.8, -0.6, 0, Math.PI * 2); c.fill();
}

function frame(c, t) {
  c.clearRect(0, 0, W, H);
  const th = (t / 1000) * (Math.PI * 2 / TURN_S);                       // keeps turning, never stops
  const tilt = TILT + Math.sin(t / 1000 * 1.3) * (4 * Math.PI / 180);    // and nods a little
  const head = axisAt(128, th, tilt);
  drawStand(c);
  drawMic(c, th, tilt);
  return head;
}

export function initHeroMic() {
  const cv = document.getElementById('heroMicCanvas');
  if (!cv || !cv.getContext) return;
  const c = cv.getContext('2d');
  const calm = matchMedia('(prefers-reduced-motion: reduce)');
  const fit = () => {
    const r = cv.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
    if (!r.width) return false;
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    c.setTransform(cv.width / W, 0, 0, cv.height / H, 0, 0);
    return true;
  };
  const visible = () => !document.hidden && cv.offsetParent !== null && !!cv.closest('.screen.active, .screen.leaving');
  let raf = 0;
  const tick = t => { raf = 0; if (!visible()) return; frame(c, t); if (!calm.matches) raf = requestAnimationFrame(tick); };
  const start = () => { if (!raf && visible() && fit()) raf = requestAnimationFrame(tick); };
  new ResizeObserver(() => { if (fit()) frame(c, performance.now()); start(); }).observe(cv);
  // Home comes on screen (after log in, or back from another screen) / tab comes back: restart the
  // loop (it stops itself while hidden). Home's section is "active" from the start and only the app
  // view around it is shown at log in, so watch both, plus the canvas itself coming into view.
  new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) start(); }).observe(cv);
  const mo = new MutationObserver(start);
  mo.observe(cv.closest('.screen') || document.body, { attributes: true, attributeFilter: ['class'] });
  const app = cv.closest('#viewApp');
  if (app) mo.observe(app, { attributes: true, attributeFilter: ['hidden'] });
  document.addEventListener('visibilitychange', start);
  calm.addEventListener('change', start);
  start();
}
