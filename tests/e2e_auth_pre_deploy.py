"""Pre-deploy E2E auth validation (Playwright)

Runs against BASE_URL (default http://localhost:3000).
Validates:
- /dashboard without token => ends up on /login
- wrong password => stays on /login with error
- correct owner creds => /dashboard
- /api/auth/me returns 200 with token
- invalid token => redirected to /login (401 logout)

Usage:
  python /app/tests/e2e_auth_pre_deploy.py
  BASE_URL=https://your-url python /app/tests/e2e_auth_pre_deploy.py
"""

import asyncio
import json
import os
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright


def _read_backend_env():
    env = {}
    try:
        with open("/app/backend/.env", "r") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return env


async def main():
    start = time.time()
    base_url = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")

    be_env = _read_backend_env()
    owner_user = os.environ.get("OWNER_USERNAME") or be_env.get("OWNER_USERNAME") or "owner"
    owner_pass = os.environ.get("OWNER_PASSWORD") or be_env.get("OWNER_PASSWORD") or ""

    if not owner_pass:
        raise RuntimeError("OWNER_PASSWORD not set (set env var or backend/.env)")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()

        # 1) /dashboard without token => login
        await page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        if "/login" not in page.url:
            # guard may render login without changing URL; accept if login form exists
            login_present = await page.locator("text=Login").first.is_visible()
            if not login_present:
                raise AssertionError(f"Expected redirect to /login; url={page.url}")

        # 2) wrong password
        await page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        await page.get_by_label("Username or Email", exact=True).fill(owner_user)
        await page.get_by_label("Password", exact=True).fill("WRONG_PASSWORD")
        await page.get_by_role("button", name="Sign In").click()
        await page.wait_for_timeout(1200)
        if "/login" not in page.url:
            raise AssertionError("Wrong-password login should not leave /login")

        # 3) correct login
        await page.get_by_label("Password", exact=True).fill(owner_pass)
        await page.get_by_role("button", name="Sign In").click()
        await page.wait_for_timeout(1500)
        if "/dashboard" not in page.url:
            raise AssertionError(f"Expected /dashboard after login; url={page.url}")

        # 4) /api/auth/me returns 200 with token
        # use fetch from browser context
        me = await page.evaluate(
            """async () => {
              const token = localStorage.getItem('auth_token_v2');
              const api = (window.__HAVEN_API_BASE__ || '') + '/api/auth/me';
              const res = await fetch(api, { headers: { Authorization: `Bearer ${token}` }});
              return { status: res.status, body: await res.text() };
            }"""
        )
        if int(me["status"]) != 200:
            raise AssertionError(f"/api/auth/me should be 200, got {me['status']} body={me['body'][:200]}")

        # 5) invalid token => logout + login
        await page.evaluate("localStorage.setItem('auth_token_v2','invalid')")
        await page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
        await page.wait_for_timeout(1200)
        if "/login" not in page.url:
            # same acceptance as above
            login_present = await page.locator("text=Login").first.is_visible()
            if not login_present:
                raise AssertionError("Expected logout+redirect to login after invalid token")

        await browser.close()

    elapsed = time.time() - start
    print(json.dumps({"ok": True, "base_url": base_url, "seconds": round(elapsed, 2)}))


if __name__ == "__main__":
    asyncio.run(main())
