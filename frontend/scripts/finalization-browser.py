"""Disposable REAL Chromium/Vite/uvicorn integration (no request interception).

Run from the repository root: python frontend/scripts/finalization-browser.py
Only synthetic offline SQLite rows are written. No agent, SSH configuration,
installer, provisioning POST, or provisioning worker is started. Artifacts are
retained in the printed output directory; the database is always deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Disposable-browser-only-42!"
HOST_ID = "browser-host-online"
JOB_ID = "browser-job-failed"
TEMP_ROOT = Path("C:/Users/user/AppData/Local/Temp/opencode")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def seed() -> None:
    """Import DB wiring only AFTER the disposable environment is installed."""
    sys.path.insert(0, str(ROOT))
    from backend.app.core.db import create_all, engine, session_scope
    from backend.app.core.security import hash_operator_password
    from backend.app.models import (
        DeploymentOperation,
        DeploymentTemplate,
        Host,
        HostEvent,
        InventorySnapshot,
        ManagedDeployment,
        Operator,
        ProvisioningConnection,
        ProvisioningJob,
        ProvisioningTarget,
        ProvisioningValidation,
        Telemetry,
    )

    create_all()
    now = datetime.now(timezone.utc)
    stamp = int(now.timestamp())
    with session_scope() as db:
        for role in ("ADMIN", "VIEWER"):
            db.add(
                Operator(
                    id=f"browser-{role.lower()}",
                    username=f"browser-{role.lower()}",
                    role=role,
                    password_hash=hash_operator_password(PASSWORD),
                )
            )
        db.add(
            Operator(
                id="browser-other",
                username="browser-other",
                role="ADMIN",
                password_hash=hash_operator_password(PASSWORD),
            )
        )
        for name, age, env, revoked in (
            ("online", 0, "PRIVATE", False),
            ("stale", 180, "PUBLIC-CLOUD", False),
            ("offline", 1800, "PRIVATE", False),
            ("revoked", 0, "PRIVATE", True),
        ):
            db.add(
                Host(
                    id=f"browser-host-{name}",
                    hostname=f"synthetic-{name}",
                    agent_token_hash="0" * 64,
                    enrollment_status="ENROLLED",
                    last_seen_at=now - timedelta(seconds=age),
                    last_telemetry_at=now - timedelta(seconds=age),
                    is_revoked=revoked,
                    revoked_at=now if revoked else None,
                    environment=env,
                    platform="Linux",
                    platform_release="synthetic",
                    agent_version="browser-fixture",
                    agent_mode="telemetry-only",
                    cpu_cores=4,
                    total_memory_bytes=8 * 2**30,
                )
            )
        db.flush()
        db.add(
            Telemetry(
                host_id=HOST_ID,
                recorded_at=now,
                cpu_percent=23.5,
                memory_used_bytes=2**30,
                memory_total_bytes=8 * 2**30,
                disk_used_bytes=10 * 2**30,
                disk_total_bytes=40 * 2**30,
                memory_used_percent=12.5,
                disk_used_percent=25,
            )
        )
        db.add(HostEvent(host_id=HOST_ID, event="ENROLLED", actor="synthetic-fixture"))
        db.add(
            InventorySnapshot(host_id=HOST_ID, observed_at=now, containers_json="[]")
        )
        db.add(
            DeploymentTemplate(
                key="browser-fixture",
                name="Synthetic fixture",
                image="never-pulled:synthetic",
                container_port=8080,
                host_port=18080,
            )
        )
        db.flush()
        db.add(
            ManagedDeployment(
                id="browser-deployment",
                host_id=HOST_ID,
                template_key="browser-fixture",
                container_name="never-created",
            )
        )
        db.flush()
        for i in range(65):
            at = now - timedelta(minutes=i)
            db.add(
                DeploymentOperation(
                    id=f"browser-operation-{i:03d}",
                    deployment_id="browser-deployment",
                    host_id=HOST_ID,
                    op_type="DEPLOY",
                    status="FAILED" if i % 3 == 0 else "SUCCEEDED",
                    created_at=at,
                    updated_at=at,
                    completed_at=at,
                    error_code="SYNTHETIC_FAILURE" if i % 3 == 0 else None,
                    error_message="Offline synthetic operation" if i % 3 == 0 else None,
                )
            )
        # Disabled metadata mirror only: NEVER a configured SSH target.
        db.add(
            ProvisioningConnection(
                id="browser-connection",
                provider="GENERIC_LINUX",
                display_name="Disabled synthetic mirror",
                policy_hash="0" * 64,
                enabled=False,
            )
        )
        db.add(
            ProvisioningTarget(
                id="browser-target",
                connection_id="browser-connection",
                canonical_key="synthetic:no-network",
                mapping_status="UNMAPPED",
            )
        )
        for i in range(66):
            job_id = JOB_ID if i == 0 else f"browser-history-{i:03d}"
            actor = "browser-other" if i == 65 else "browser-admin"
            validation = f"browser-validation-{i:03d}"
            db.add(
                ProvisioningValidation(
                    id=validation,
                    target_id="browser-target",
                    actor_id=actor,
                    plan_json="{}",
                    plan_hash="0" * 64,
                    config_revision=1,
                    mapping_revision=0,
                    observed_identity_hash="0" * 64,
                    created_at=stamp - i,
                    expires_at=stamp + 60,
                    consumed_by_job_id=job_id,
                )
            )
            db.add(
                ProvisioningJob(
                    id=job_id,
                    target_id="browser-target",
                    operation="INSTALL",
                    validation_id=validation,
                    requester_id=actor,
                    approval_hash="0" * 64,
                    approval_expires_at=stamp + 60,
                    plan_json="{}",
                    state="FAILED",
                    step="REVALIDATE",
                    reason_code="SYNTHETIC_OFFLINE",
                    dispatch_blocked=True,
                    deadline_at=stamp,
                    created_at=stamp - i,
                    updated_at=stamp - i,
                    completed_at=stamp - i,
                )
            )
    engine.dispose()


def wait_ready(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Owned server exited {process.returncode}: {url}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.15)
    raise TimeoutError(url)


def journeys(origin: str, output: Path, database: Path) -> dict:
    from playwright.sync_api import expect, sync_playwright

    results: dict = {
        "mode": "REAL browser + backend; no interception",
        "checks": [],
        "console_errors": [],
        "http_errors": [],
        "requests": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: results["console_errors"].append(str(error)))
        page.on(
            "response",
            lambda response: (
                results["http_errors"].append(
                    {"url": response.url, "status": response.status}
                )
                if response.status >= 400
                else None
            ),
        )
        page.on(
            "request",
            lambda request: (
                results["requests"].append(
                    {"method": request.method, "url": request.url}
                )
                if "/api/" in request.url
                else None
            ),
        )

        def check(name, action):
            try:
                action()
                results["checks"].append({"name": name, "status": "PASS"})
                print(f"PASS {name}", flush=True)
            # Independent checks must record failures and continue the suite.
            except Exception as error:  # noqa: BLE001
                results["checks"].append(
                    {"name": name, "status": "FAIL", "error": str(error)}
                )
                page.screenshot(
                    path=str(output / f"failure-{len(results['checks'])}.png"),
                    full_page=True,
                )
                (output / f"failure-{len(results['checks'])}.html").write_text(
                    page.content(), encoding="utf-8"
                )
                print(f"FAIL {name}: {error}", flush=True)

        def visit(path):
            page.goto(origin + path)
            page.wait_for_load_state("networkidle")

        def login(role="admin"):
            page.get_by_label("Username", exact=True).fill(f"browser-{role}")
            page.get_by_label("Password", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(
                page.get_by_role("heading", name="Sign in to NimbusOps")
            ).to_have_count(0)
            page.wait_for_load_state("networkidle")

        def authentication():
            visit("/servers")
            expect(page).to_have_url(origin + "/login")
            page.get_by_label("Username", exact=True).fill("browser-admin")
            page.get_by_label("Password", exact=True).fill("wrong-password")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("invalid credentials")
            login()
            expect(page).to_have_url(origin + "/servers")
            page.reload()
            expect(
                page.get_by_role("heading", name="Servers", exact=True)
            ).to_be_visible()
            cookies = context.cookies()
            cookie = next(c for c in cookies if c["name"] == "nimbusops_session")
            assert cookie["httpOnly"] and cookie["sameSite"] == "Strict", cookie
            assert not page.evaluate(
                "Object.keys(localStorage).some(k => /token|session/i.test(k))"
            )

        check(
            "login failure, protected redirect, persistence and HttpOnly cookie",
            authentication,
        )

        def expired_session():
            # Revoke only the disposable operator's sessions directly offline.
            with sqlite3.connect(database) as db:
                db.execute(
                    "UPDATE operator_sessions SET revoked_at = ? WHERE operator_id = ?",
                    (datetime.now(timezone.utc).isoformat(), "browser-admin"),
                )
            visit("/settings")
            expect(page).to_have_url(origin + "/login")
            login()
            expect(
                page.get_by_role("heading", name="Settings", exact=True)
            ).to_be_visible()

        check(
            "real server-revoked session redirects and reauthenticates", expired_session
        )
        check(
            "overview real fleet",
            lambda: (
                visit("/"),
                expect(
                    page.get_by_test_id("fleet-table").get_by_role(
                        "link", name="synthetic-online", exact=True
                    )
                ).to_be_visible(),
            ),
        )

        def fleet():
            visit("/servers")
            expect(page.locator("article")).to_have_count(4)
            page.get_by_placeholder("Search by server name…").fill("OFFLINE")
            expect(page.locator("article")).to_have_count(1)
            expect(
                page.get_by_role("link", name="synthetic-offline", exact=True)
            ).to_be_visible()
            page.get_by_placeholder("Search by server name…").fill(
                "no-matching-synthetic"
            )
            expect(page.get_by_text("No servers match your search.")).to_be_visible()
            page.get_by_placeholder("Search by server name…").fill("")
            page.get_by_role("button", name="PUBLIC-CLOUD", exact=True).click()
            expect(page.locator("article")).to_have_count(1)
            expect(
                page.get_by_role("link", name="synthetic-stale", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="ALL", exact=True).click()
            with page.expect_response(
                lambda response: "/api/v1/hosts" in response.url
                and response.status == 200
            ):
                page.get_by_role("button", name="Refresh", exact=True).click()
            expect(page.locator("article")).to_have_count(4)

        check(
            "server list search, empty state, environment filter and real refresh",
            fleet,
        )

        for tab, text in (
            ("Overview", "Connectivity"),
            ("Monitoring", "Recent telemetry"),
            ("Deployments", "never-created"),
            ("Activity", "Showing 50 of 65 operations."),
        ):

            def detail(tab=tab, text=text):
                visit(f"/servers/{HOST_ID}?tab={tab}")
                expect(page.get_by_role("tab", name=tab, exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                expect(page.get_by_text(text, exact=True).first).to_be_visible()

            check(f"host detail {tab} tab", detail)

        def dialog():
            visit(f"/servers/{HOST_ID}")
            opener = page.get_by_role("button", name="Revoke host", exact=True)
            opener.click()
            modal = page.get_by_role("dialog")
            expect(modal).to_be_visible()
            expect(
                modal.get_by_role("button", name="Confirm revoke", exact=True)
            ).to_be_disabled()
            page.keyboard.press("Escape")
            expect(modal).to_have_count(0)
            expect(opener).to_be_focused()

        check(
            "typed destructive confirmation, Escape dismissal and focus restoration (no write)",
            dialog,
        )

        def activity():
            visit("/activity")
            expect(page.locator("article")).to_have_count(50)
            page.get_by_role("button", name="Load older", exact=True).click()
            expect(page.locator("article")).to_have_count(65)
            page.get_by_role("button", name="FAILED", exact=True).click()
            expect(page.locator("article")).to_have_count(22)
            expect(
                page.get_by_text("Showing 22 of 22 operations.", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="RUNNING", exact=True).click()
            expect(
                page.get_by_text("No operations recorded for this filter.")
            ).to_be_visible()

        check("activity paging, server-side status filter and empty state", activity)

        def settings():
            visit("/settings")
            expect(page.get_by_test_id("settings-account")).to_contain_text(
                "browser-admin"
            )
            expect(page.get_by_test_id("settings-account")).to_contain_text("ADMIN")
            page.get_by_role("button", name="Recheck", exact=True).click()
            page.wait_for_load_state("networkidle")
            buttons = page.get_by_role("button", name="Copy", exact=False)
            assert (
                buttons.count() > 0
            ), "Settings should expose deployment reference copy controls"
            buttons.first.click()
            assert page.evaluate("navigator.clipboard.readText()"), "Clipboard is empty"

        check("Settings account, live probes, recheck and real clipboard", settings)

        def onboarding():
            visit("/servers/new")
            expect(
                page.get_by_role("heading", name="Add Server", exact=True)
            ).to_be_visible()
            expect(
                page.get_by_text("No authorized targets", exact=False)
            ).to_be_visible()
            assert context.request.get(
                origin + "/api/v1/provisioning/targets"
            ).json() == {"targets": []}
            page.get_by_role("button", name="Manual Bootstrap", exact=True).click()
            page.wait_for_load_state("networkidle")
            expect(
                page.get_by_role("button", name="Automatic Setup (recommended)")
            ).to_have_attribute("aria-pressed", "false")
            page.get_by_label("Hostname", exact=True).fill("synthetic-new-no-install")
            page.get_by_role("button", name="Continue", exact=True).click()
            expect(
                page.get_by_role("heading", name="Select Agent Mode", exact=True)
            ).to_be_visible()
            expect(page.locator('input[value="telemetry-only"]')).to_be_checked()
            # Change UI choice only; NEVER press the token-generation control.
            page.get_by_text("Docker executor", exact=True).click()
            expect(page.locator('input[value="executor"]')).to_be_checked()
            page.get_by_text("Telemetry only", exact=True).click()
            expect(page.locator('input[value="telemetry-only"]')).to_be_checked()

        check(
            "Add Server automatic empty-target and manual mode (no provisioning POST)",
            onboarding,
        )

        def job():
            response = context.request.get(
                origin + f"/api/v1/provisioning/jobs/{JOB_ID}"
            )
            assert response.status == 200, response.text()
            assert response.json()["state"] == "FAILED"
            listing = context.request.get(origin + "/api/v1/provisioning/jobs")
            results["job_history_discovery"] = {
                "status": listing.status,
                "body": listing.text(),
            }
            if listing.status == 200:
                assert any(item["id"] == JOB_ID for item in listing.json()["jobs"])
                assert listing.json()["total"] == 65
                hidden = context.request.get(
                    origin + "/api/v1/provisioning/jobs/browser-history-065"
                )
                assert hidden.status == 404, hidden.text()
                # Discover without any previously stored local job reference.
                page.evaluate("sessionStorage.removeItem('nimbusops.setup.job.v1')")
                visit("/servers/new")
                history = page.get_by_role("region", name="Setup job history")
                expect(
                    history.get_by_text("Job ID: " + JOB_ID, exact=True)
                ).to_be_visible()
                expect(history.locator("li")).to_have_count(50)
                history.get_by_role(
                    "button", name="Load older setup jobs", exact=True
                ).click()
                expect(history.locator("li")).to_have_count(65)
                expect(
                    history.get_by_text("Job ID: browser-history-065", exact=True)
                ).to_have_count(0)
                history.get_by_role(
                    "button", name="Refresh job history", exact=True
                ).click()
                expect(
                    history.get_by_role("button", name="Inspect " + JOB_ID, exact=True)
                ).to_be_enabled()
                history.get_by_role(
                    "button", name="Inspect " + JOB_ID, exact=True
                ).click()
                expect(page.get_by_text("Job: " + JOB_ID, exact=True)).to_be_visible()
                page.get_by_role(
                    "button", name="Refresh job status", exact=True
                ).click()
                expect(page.get_by_text("Status: FAILED", exact=True)).to_be_visible()
            # Verify persisted single-job recovery independently of history.
            page.evaluate(
                "id => sessionStorage.setItem('nimbusops.setup.job.v1', id)", JOB_ID
            )
            visit("/servers/new")
            expect(page.get_by_text("Status: FAILED", exact=True)).to_be_visible()
            expect(
                page.get_by_text("Reason: SYNTHETIC_OFFLINE", exact=True).first
            ).to_be_visible()

        check("offline seeded terminal job GET and browser recovery", job)

        def csrf():
            response = context.request.post(origin + "/api/v1/operators/session/logout")
            assert response.status == 403, response.text()
            assert context.request.get(origin + "/api/v1/operators/me").status == 200
            token = context.request.get(
                origin + "/api/v1/operators/session/csrf"
            ).json()["csrf_token"]
            response = context.request.post(
                origin + "/api/v1/operators/session/logout",
                headers={"Origin": "https://untrusted.invalid", "X-CSRF-Token": token},
            )
            assert response.status == 403, response.text()

        check(
            "real session rejects missing CSRF and untrusted origin without logout",
            csrf,
        )

        def missing_host():
            visit("/servers/does-not-exist")
            expect(page.get_by_role("alert")).to_contain_text("Host not found")

        check("real backend 404 error panel", missing_host)

        def mobile():
            page.set_viewport_size({"width": 390, "height": 844})
            visit("/servers")
            expect(
                page.get_by_role("heading", name="Servers", exact=True)
            ).to_be_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), "Mobile viewport horizontal overflow"
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement !== document.body")
            page.screenshot(path=str(output / "mobile-servers.png"), full_page=True)
            page.set_viewport_size({"width": 1280, "height": 900})

        check("mobile fleet layout and keyboard focus", mobile)

        def viewer():
            error_start = len(results["http_errors"])
            visit("/settings")
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(page).to_have_url(origin + "/login")
            assert context.request.get(origin + "/api/v1/operators/me").status == 401
            visit("/servers")
            login("viewer")
            expect(
                page.get_by_role("heading", name="Servers", exact=True)
            ).to_be_visible()
            expect(
                page.get_by_role("button", name="Add Server", exact=True)
            ).to_have_count(0)
            assert (
                context.request.get(origin + "/api/v1/provisioning/targets").status
                == 403
            )
            token = context.request.get(
                origin + "/api/v1/operators/session/csrf"
            ).json()["csrf_token"]
            response = context.request.patch(
                origin + f"/api/v1/hosts/{HOST_ID}",
                data={"environment": "PUBLIC-CLOUD"},
                headers={"X-CSRF-Token": token, "Origin": origin},
            )
            assert response.status == 403, response.text()
            visit("/servers/new")
            expect(
                page.get_by_role("heading", name="Add Server", exact=True)
            ).to_have_count(0)
            assert not [
                r
                for r in results["http_errors"][error_start:]
                if r["status"] == 403 and "bootstrap-tokens" in r["url"]
            ], "Viewer requested ADMIN-only bootstrap-token feed"

        check(
            "logout revocation, viewer read-only UI and backend authorization", viewer
        )

        def offline_fault():
            visit("/servers")
            context.set_offline(True)
            try:
                page.get_by_role("button", name="Refresh", exact=True).click()
                expect(
                    page.get_by_role("button", name="Retry", exact=True)
                ).to_be_visible()
            finally:
                context.set_offline(False)
            page.get_by_role("button", name="Retry", exact=True).click()
            expect(
                page.get_by_role("link", name="synthetic-online", exact=True)
            ).to_be_visible()

        check(
            "EXPLICIT browser-network-offline fault and live Retry recovery",
            offline_fault,
        )

        def isolated_busy_dialog():
            # SAFE ISOLATED COMPONENT HARNESS, not a core route or API mock.
            # Load Vite's real refresh preamble before importing its TSX module.
            component = context.new_page()
            component_api_requests = []
            component.on(
                "request",
                lambda request: (
                    component_api_requests.append(request.url)
                    if "/api/" in request.url
                    else None
                ),
            )
            try:
                component.goto(origin + "/@vite/client")
                component.evaluate("""async () => {
                      const RefreshRuntime = (await import('/@react-refresh')).default;
                      RefreshRuntime.injectIntoGlobalHook(window);
                      window.$RefreshReg$ = () => {};
                      window.$RefreshSig$ = () => type => type;
                      window.__vite_plugin_react_preamble_installed__ = true;
                      const reactModule = await import('/node_modules/.vite/deps/react.js');
                      const React = reactModule.default ?? reactModule;
                      const clientModule = await import('/node_modules/.vite/deps/react-dom_client.js');
                      const {createRoot} = clientModule.default ?? clientModule;
                      const {ConfirmDialog} = await import('/src/ui/ConfirmDialog.tsx');
                      document.body.innerHTML = '<div id="isolated-component-root"></div>';
                      function Harness() {
                        const [open, setOpen] = React.useState(false);
                        const [busy, setBusy] = React.useState(false);
                        window.finishIsolatedBusyDialog = () => {
                          setBusy(false);
                          setOpen(false);
                        };
                        return React.createElement(React.Fragment, null,
                          React.createElement('button', {onClick: () => setOpen(true)}, 'Open isolated dialog'),
                          React.createElement('button', null, 'Outside focus sentinel'),
                          React.createElement(ConfirmDialog, {
                            isOpen: open, busy, title: 'Isolated local-only confirmation',
                            confirmLabel: 'Confirm local state',
                            onConfirm: () => setBusy(true), onClose: () => setOpen(false)
                          })
                        );
                      }
                      createRoot(document.getElementById('isolated-component-root'))
                        .render(React.createElement(Harness));
                    }""")
                trigger = component.get_by_role(
                    "button", name="Open isolated dialog", exact=True
                )
                trigger.focus()
                expect(trigger).to_be_focused()
                trigger.click()
                modal = component.get_by_role("dialog")
                expect(modal).to_be_visible()
                expect(modal.get_by_role("button", name="Cancel")).to_be_focused()
                component.get_by_role(
                    "button", name="Confirm local state", exact=True
                ).click()
                expect(modal.locator("button:disabled")).to_have_count(2)
                expect(modal).to_be_focused()
                for key in ("Tab", "Shift+Tab", "Tab", "Shift+Tab"):
                    component.keyboard.press(key)
                    assert modal.evaluate(
                        "el => el === document.activeElement || el.contains(document.activeElement)"
                    ), f"Busy focus escaped after {key}"
                component.keyboard.press("Escape")
                expect(modal).to_be_visible()
                expect(modal).to_be_focused()
                component.evaluate("window.finishIsolatedBusyDialog()")
                expect(modal).to_have_count(0)
                expect(trigger).to_be_focused()
                assert not component_api_requests, component_api_requests
                component.screenshot(path=str(output / "isolated-dialog-restored.png"))
            finally:
                component.close()

        check(
            "SAFE ISOLATED actual ConfirmDialog: enabled-to-busy focus, Tab/ShiftTab containment, Escape guard and restoration; local state only",
            isolated_busy_dialog,
        )
        prohibited = [
            r
            for r in results["requests"]
            if r["method"] != "GET" and "/provisioning/" in r["url"]
        ]
        assert not prohibited, prohibited
        context.tracing.stop(path=str(output / "trace.zip"))
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Artifact directory (default new OS temp directory)"
    )
    args = parser.parse_args()
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    output = args.output or Path(
        tempfile.mkdtemp(prefix="nimbusops-real-browser-", dir=TEMP_ROOT)
    )
    output.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen] = []
    handles = []
    print(f"Artifacts: {output}", flush=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="nimbusops-disposable-db-", dir=TEMP_ROOT
        ) as scratch:
            api_port, web_port = free_port(), free_port()
            while api_port == web_port:
                web_port = free_port()
            origin = f"http://127.0.0.1:{web_port}"
            # Do not inherit any user deployment policy/configuration. Backend cwd
            # is the empty scratch folder so pydantic cannot read repository .env.
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.upper().startswith("NIMBUSOPS_")
            }
            env.update(
                NIMBUSOPS_DATABASE_URL=f"sqlite:///{Path(scratch).as_posix()}/browser.sqlite3",
                NIMBUSOPS_TOKEN_PEPPER="synthetic-disposable-browser-signing-key-only",
                NIMBUSOPS_ENROLLMENT_MODE="disabled",
                NIMBUSOPS_SESSION_COOKIE_SECURE="false",
                NIMBUSOPS_BROWSER_ORIGINS=origin,
                NIMBUSOPS_CORS_ORIGINS=origin,
                PYTHONPATH=str(ROOT),
                API_PROXY_TARGET=f"http://127.0.0.1:{api_port}",
            )
            # Seed in an isolated subprocess, also from the empty scratch cwd.
            seeded = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import runpy; m=runpy.run_path("
                    + repr(str(Path(__file__).resolve()))
                    + "); m['seed']()",
                ],
                check=False,
                env=env,
                cwd=scratch,
                capture_output=True,
                text=True,
            )
            if seeded.returncode:
                raise RuntimeError(seeded.stderr)
            commands = [
                (
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "backend.app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    scratch,
                    "backend.log",
                ),
                (
                    [
                        "node",
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(web_port),
                        "--strictPort",
                    ],
                    str(ROOT / "frontend"),
                    "vite.log",
                ),
            ]
            try:
                for command, cwd, log in commands:
                    handle = (output / log).open("w", encoding="utf-8")
                    handles.append(handle)
                    processes.append(
                        subprocess.Popen(
                            command,
                            cwd=cwd,
                            env=env,
                            stdout=handle,
                            stderr=subprocess.STDOUT,
                        )
                    )
                wait_ready(f"http://127.0.0.1:{api_port}/api/v1/health", processes[0])
                wait_ready(origin, processes[1])
                results = journeys(origin, output, Path(scratch) / "browser.sqlite3")
                results["origin"] = origin
                results["backend_port"] = api_port
                (output / "results.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8"
                )
                failed = [c for c in results["checks"] if c["status"] == "FAIL"]
                print(
                    f"{len(results['checks']) - len(failed)} passed; {len(failed)} failed",
                    flush=True,
                )
                return 1 if failed or results["console_errors"] else 0
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                for handle in handles:
                    handle.close()
                print(
                    "Owned Vite/uvicorn processes stopped; disposable DB removed on scope exit.",
                    flush=True,
                )
    except Exception:  # noqa: BLE001 - CLI failure boundary preserves diagnostics
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
