# HAVEN – Pre‑Deploy Validation (Auth Regression‑Proof)

**Last Verified:** 2026-01-01 ✅ ALL TESTS PASSING

This checklist is **mandatory before any deploy**.

**Deployment rule:** Always use **Replace Existing Deployment** + **Keep existing database**.

## 0) Prerequisites (must be set)

Backend env vars (minimum):
- `JWT_SECRET_KEY` (required)
- `OWNER_USERNAME=owner`
- `OWNER_PASSWORD=Haven!2026_Strong#Auth`
- `OWNER_EMAIL=owner@haven.local`

> Email is intentionally NOT configured right now → password recovery runs in **DEMO MODE**.

---

## 1) Backend – Auth regression test suite

Run from repo root:

```bash
cd /app/backend
pytest -q tests/test_auth_regression.py
```

Expected:
- ✅ All tests pass
- ❌ Any failure blocks deploy

---

## 2) Frontend – E2E auth smoke (local)

Run from repo root:

```bash
python /app/tests/e2e_auth_pre_deploy.py
```

This validates:
- /dashboard without token → redirect to /login
- wrong password → stays on /login
- correct owner login → /dashboard
- /api/auth/me → 200 when logged in
- invalid token → auto logout → /login

---

## 3) Post‑deploy 60s smoke test (external URL)

Set `BASE_URL` to the deployed frontend URL and run:

```bash
BASE_URL=https://YOUR_DEPLOYED_URL python /app/tests/e2e_auth_pre_deploy.py
```

Time budget: **<= 60 seconds**.

---

## 4) Manual spot‑check (optional but recommended)

1) Open `/login` → login as `owner`.
2) Navigate to `/dashboard`.
3) Open DevTools → Application → Local Storage:
   - Confirm `auth_token_v2` exists.
4) Corrupt the token:
   - `localStorage.setItem('auth_token_v2','invalid')`
   - reload `/dashboard`
   - confirm redirect to `/login`.
