/**
 * Bridge from Server Actions to the Socket.IO instance owned by server.js.
 *
 * Both run in the same Node process (custom server), so the io instance is
 * shared via globalThis. Every helper is a no-op when realtime isn't available
 * — e.g. under `next start`, or during build — so actions never fail because
 * of the socket layer.
 */

// Connected to the FastAPI Socket.IO backend.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_SECRET = process.env.INTERNAL_SECRET || 'dev_secret';

/** True when the custom server is running and sockets are available. */
export function isRealtimeEnabled(): boolean {
  // Always assume true, or check a process flag if needed.
  return true;
}

function safeEmit(room: string, event: string, payload?: unknown) {
  fetch(`${BACKEND_URL}/api/internal/emit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      secret: INTERNAL_SECRET,
      room,
      event,
      data: payload
    })
  }).catch(err => {
    console.error(`[realtime] emit ${event} failed:`, err);
  });
}

/** Push to one user across all their open tabs. */
export function emitToUser(userId: string, event: string, payload?: unknown) {
  safeEmit(`user:${userId}`, event, payload);
}

/** Push to every member of a chat group. */
export function emitToGroup(groupId: string, event: string, payload?: unknown) {
  safeEmit(`group:${groupId}`, event, payload);
}

/** Push to everyone signed in. */
export function emitToOrg(event: string, payload?: unknown) {
  safeEmit('org', event, payload);
}

/** Push to several users at once. */
export function emitToUsers(userIds: string[], event: string, payload?: unknown) {
  for (const id of new Set(userIds)) emitToUser(id, event, payload);
}
