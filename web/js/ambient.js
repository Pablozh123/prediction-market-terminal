// Ambient motion on the landing: the probability river behind the hero and
// the market wire's marquee under it. The river is ornament and says so with
// its form — no axes, no labels, no numbers, so it cannot be read as a
// measurement. The wire's rows are real (they come from the same 30 s poll
// as the Markets page); only its movement lives here.
//
// State sits at module level on purpose: render() rebuilds the DOM every
// poll, and the drift must not restart every 30 s. mount() re-attaches the
// running engine to the fresh elements; one requestAnimationFrame loop
// serves both pieces and idles when neither is on the page (hidden tabs
// pause it for free — the browser stops delivering frames).

let laueft = false;
let cv = null, ctx = null, cw = 0, ch = 0;
let walkers = null;
let wireX = 0, wireHalb = 0;
let farben = null;

const ANZAHL = 46;      // Pfade im Fluss
const FENSTER = 240;    // Punkte je Pfad
const WIRE_TEMPO = 0.5; // px pro Frame

function reduziert() {
  try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
}

// Die Canvas kennt kein var(): die Werte kommen bei jedem Mount aus den
// berechneten Tokens, darum folgt der Fluss auch dem Theme-Wechsel.
function leseFarben() {
  const cs = getComputedStyle(document.documentElement);
  const t = (name, ersatz) => (cs.getPropertyValue(name) || '').trim() || ersatz;
  return {
    ink: t('--ink', '234, 230, 220'),
    accent: t('--accent', '#D9A648'),
    pos: t('--pos-rgb', '105, 180, 126'),
    neg: t('--neg-rgb', '217, 95, 82')
  };
}

function neuerPfad(gefuehrt) {
  return {
    hist: [], y: 0.25 + Math.random() * 0.5,
    // Versteckter Drift zum eigenen Ausgang — irgendwann resolved jeder Pfad.
    bias: (Math.random() < 0.5 ? -1 : 1) * (0.0004 + Math.random() * 0.0012),
    v: 0, alpha: 1, fertig: false, blitz: 0, gefuehrt: !!gefuehrt, ton: Math.random()
  };
}

function schritt(p, ersetzen) {
  p.v = p.v * 0.94 + (Math.random() - 0.5) * 0.006 + p.bias;
  p.y = Math.max(0, Math.min(1, p.y + p.v));
  p.hist.push(p.y);
  if (p.hist.length > FENSTER) p.hist.shift();
  if (!p.fertig && (p.y > 0.988 || p.y < 0.012)) { p.fertig = true; p.blitz = 1; }
  if (p.fertig) {
    p.alpha -= 0.012;
    if (p.alpha <= 0) ersetzen(p);
  }
}

function malen(bewegen) {
  if (!cv || !cv.isConnected || !ctx) return;
  if (!walkers) { walkers = []; for (let i = 0; i < ANZAHL; i++) walkers.push(neuerPfad(i === 7)); }
  const pad = 26;
  const Y = (p) => pad + (1 - p) * (ch - 2 * pad);
  const dx = cw / (FENSTER - 1);
  ctx.clearRect(0, 0, cw, ch);
  const ersetzen = (p) => { walkers[walkers.indexOf(p)] = neuerPfad(p.gefuehrt); };
  for (const p of walkers) {
    if (bewegen) schritt(p, ersetzen);
    if (p.hist.length < 2) continue;
    const oben = p.y > 0.5;
    ctx.beginPath();
    for (let i = 0; i < p.hist.length; i++) {
      const x = cw - (p.hist.length - 1 - i) * dx;
      if (i) ctx.lineTo(x, Y(p.hist[i])); else ctx.moveTo(x, Y(p.hist[i]));
    }
    if (p.gefuehrt) { ctx.strokeStyle = 'rgba(' + hexZuRgb(farben.accent) + ',' + (0.75 * p.alpha) + ')'; ctx.lineWidth = 1.5; }
    else if (p.fertig) { ctx.strokeStyle = 'rgba(' + (oben ? farben.pos : farben.neg) + ',' + (0.5 * p.alpha) + ')'; ctx.lineWidth = 1.1; }
    else { ctx.strokeStyle = 'rgba(' + farben.ink + ',' + (0.07 + 0.05 * p.ton) + ')'; ctx.lineWidth = 1; }
    ctx.stroke();
    if (p.fertig && p.blitz > 0) {
      const ey = Y(p.hist[p.hist.length - 1]);
      ctx.beginPath(); ctx.arc(cw - 6, ey, 3 + 16 * (1 - p.blitz), 0, 7);
      ctx.strokeStyle = 'rgba(' + (oben ? farben.pos : farben.neg) + ',' + (0.55 * p.blitz) + ')';
      ctx.lineWidth = 1.3; ctx.stroke();
      ctx.beginPath(); ctx.arc(cw - 6, ey, 2.2, 0, 7);
      ctx.fillStyle = 'rgba(' + (oben ? farben.pos : farben.neg) + ',0.9)'; ctx.fill();
      if (bewegen) p.blitz -= 0.02;
    }
  }
}

function hexZuRgb(hex) {
  const n = parseInt(String(hex).replace('#', ''), 16);
  return ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255);
}

function canvasMassen() {
  if (!cv) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = cv.getBoundingClientRect();
  cw = r.width; ch = r.height;
  cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr);
  ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function wireSchieben(bewegen) {
  const row = document.getElementById('wire-row');
  if (!row || !row.isConnected) return;
  if (!wireHalb) wireHalb = row.scrollWidth / 2;
  if (bewegen) { wireX -= WIRE_TEMPO; if (-wireX >= wireHalb) wireX = 0; }
  row.style.transform = 'translateX(' + wireX + 'px)';
}

// Bei reduzierter Bewegung wird genau ein Standbild gemalt und das Band an
// seine Position gesetzt — danach ruht der Loop, bis ein Mount ihn weckt.
let standbildNoetig = true;

function tick() {
  const still = reduziert();
  if (!still) {
    malen(true);
    wireSchieben(true);
  } else if (standbildNoetig) {
    malen(false);
    wireSchieben(false);
    standbildNoetig = false;
  }
  requestAnimationFrame(tick);
}

/** Nach jedem render() aufgerufen: dockt den laufenden Motor an das frische
 *  DOM an. Auf Seiten ohne die Elemente tut der Loop nichts. */
export function mountAmbient() {
  cv = document.getElementById('river-cv');
  if (cv) { farben = leseFarben(); canvasMassen(); }
  wireHalb = 0;          // Inhalt kann sich mit dem Poll geaendert haben
  standbildNoetig = true; // frisches DOM braucht auch im Ruhezustand ein Bild
  if (!laueft) {
    laueft = true;
    window.addEventListener('resize', () => { if (cv && cv.isConnected) canvasMassen(); });
    requestAnimationFrame(tick);
  }
}
