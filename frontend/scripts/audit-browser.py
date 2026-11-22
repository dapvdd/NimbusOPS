"""Safe UI smoke: intercepted fixture API, no backend or operational requests."""
import json
from playwright.sync_api import sync_playwright, expect


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        signed_in = False
        writes = []

        def api(route):
            nonlocal signed_in
            path = route.request.url.split("/api/v1", 1)[1]
            if route.request.method != "GET":
                writes.append(path)
                if path == "/operators/session/login":
                    signed_in = True
                elif path == "/operators/session/logout":
                    signed_in = False
                else:
                    raise AssertionError("Unexpected write: " + path)
            body = {}
            status = 200
            if path == "/operators/me":
                status = 200 if signed_in else 401
                body = {"username": "audit-admin", "operator_id": "fixture", "role": "ADMIN"}
            elif "csrf" in path or "login" in path:
                body = {"csrf_token": "fixture", "role": "ADMIN"}
            elif path == "/health":
                body = {"status": "ok", "database": "ok", "version": "fixture", "build": "fixture"}
            elif path == "/ready":
                body = {"ready": True, "database": "ok"}
            elif path == "/hosts":
                body = {"hosts": [], "count": 0}
            elif path.startswith("/operations"):
                body = {"operations": [], "total": 0}
            elif path.startswith("/operators/bootstrap-tokens"):
                body = {"tokens": [], "count": 0}
            elif path == "/templates":
                body = {"templates": []}
            elif path == "/applications":
                body = {"applications": []}
            elif path == "/provisioning/targets":
                body = {"targets": []}
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

        page.route("**/api/v1/**", api)
        page.goto("http://127.0.0.1:15173", wait_until="networkidle")
        page.get_by_label("Username").fill("audit-admin")
        page.get_by_label("Password", exact=True).fill("fixture-only")
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("heading", name="Overview", exact=True)).to_be_visible()
        for label, heading in [("Servers", "Servers"), ("Deployments", "Applications"), ("Activity", "Activity"), ("Settings", "Settings")]:
            page.get_by_role("navigation", name="Primary").get_by_role("link", name=label, exact=True).click()
            expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
        page.get_by_role("button", name="Recheck", exact=True).click()
        expect(page.get_by_text("Control plane ready", exact=True)).to_be_visible()
        page.goto("http://127.0.0.1:15173/servers/new", wait_until="networkidle")
        expect(page.get_by_text("No authorized targets.", exact=False)).to_be_visible()
        page.get_by_role("button", name="Manual Bootstrap", exact=True).click()
        expect(page.get_by_role("button", name="Automatic Setup (recommended)")).to_be_visible()
        page.get_by_role("button", name="Log out", exact=True).click()
        expect(page.get_by_role("heading", name="Sign in to NimbusOps")).to_be_visible()
        assert not errors, errors
        assert writes == ["/operators/session/login", "/operators/session/logout"], writes
        print("PASS browser fixture smoke: login, all primary routes, empty states, readiness recheck, setup methods, logout; zero operational writes/page errors")
        browser.close()


if __name__ == "__main__":
    run()
