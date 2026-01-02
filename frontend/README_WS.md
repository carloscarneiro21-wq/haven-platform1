# HAVEN WebSocket (Trades Stream)

## Endpoint (Backend)
- **Path:** `/api/ws/stream`
- **Production URL format:**
  - If `REACT_APP_BACKEND_URL=https://trade-route.preview.emergentagent.com`
  - Then WS connects to:
    - `wss://trade-route.preview.emergentagent.com/api/ws/stream?token=<JWT>`

## Auth
- Browser WebSocket cannot set `Authorization` header.
- We pass JWT via query param `?token=<JWT>`.
- Backend validates JWT and closes unauthorized connections with code `4401`.

## Keepalive / Stability
### Server-side
- Server sends `{"type":"ping","ts":...}` every 30s.
- Server considers a connection stale if no `pong` (or any client message) is received for 120s.

### Client-side
- Client responds to server `ping` with `{"type":"pong", ...}`.
- Client sends its own `ping` every 25s.
- If no WS message is received for 60s, client forces reconnect.
- Reconnect: exponential backoff with jitter, capped at 30s.

## Polling fallback (safety)
- When WS is connected: **polling OFF**.
- When WS is disconnected: Trades page uses controlled polling (min 15s + cache + inFlight guard + backoff on 429).

## Optional env var
- `REACT_APP_WS_PATH` (optional)
  - Default: `/api/ws/stream`
  - Use only if a different WS path is required by a proxy.
