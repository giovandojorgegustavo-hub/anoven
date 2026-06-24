/**
 * Sonido de notificación cuando el mentor termina de responder.
 *
 * Usa Web Audio API para generar un "ding" de 2 tonos sin archivos externos.
 * Tono 1: 880Hz (A5). Tono 2: 1320Hz (E6). Duración total ~250ms.
 *
 * Se invoca solo en eventos esperados (final de streaming). No autoplay.
 */

let cachedContext: AudioContext | null = null;

function getContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (cachedContext) return cachedContext;
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext })
      .webkitAudioContext;
  if (!Ctor) return null;
  cachedContext = new Ctor();
  return cachedContext;
}

function playTone(
  ctx: AudioContext,
  freq: number,
  startAt: number,
  duration: number,
  peakGain: number,
) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0, startAt);
  gain.gain.linearRampToValueAtTime(peakGain, startAt + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
  osc.start(startAt);
  osc.stop(startAt + duration);
}

export function playReplyDoneSound(): void {
  const ctx = getContext();
  if (!ctx) return;
  // En Safari/iOS el contexto puede estar suspendido hasta primer click.
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {});
  }
  const now = ctx.currentTime;
  playTone(ctx, 880, now, 0.15, 0.08);
  playTone(ctx, 1320, now + 0.1, 0.18, 0.08);
}
