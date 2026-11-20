"""Real loopback HTTP, isolated API subprocess/database, two logical agents.

Both agents run on this development machine, NOT separate Ubuntu VMs.
Docker authorization/queue isolation is real; no Docker commands are executed.
"""

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx

from nimbusops_agent.client import Sender
from nimbusops_agent.config import Identity, load_identity, save_identity
from nimbusops_agent.main import run_cycle


def test_two_identities_reconnect_and_host_queue_isolation(tmp_path):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "NIMBUSOPS_DATABASE_URL": f"sqlite:///{tmp_path / 'uat.db'}",
           "NIMBUSOPS_ENROLLMENT_MODE": "bootstrap", "NIMBUSOPS_ENROLLMENT_TOKEN": "",
           "NIMBUSOPS_TOKEN_PEPPER": secrets.token_hex(32),
           "NIMBUSOPS_STALE_THRESHOLD_SECONDS": "1", "NIMBUSOPS_OFFLINE_THRESHOLD_SECONDS": "2"}
    password = secrets.token_urlsafe(24)
    subprocess.run([sys.executable, "-c",
                    "import sys; from backend.app.core.db import create_all; "
                    "from backend.scripts.create_operator import create_operator; "
                    "create_all(); create_operator('uat-admin', sys.stdin.read())"],
                   cwd=root, env=env, input=password, text=True, check=True)
    base = f"http://127.0.0.1:{port}"
    process = None

    def start():
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app",
                                 "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
                                cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                assert proc.poll() is None, "isolated API exited before readiness"
                try:
                    if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                        return proc
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            raise AssertionError("isolated API readiness timeout")
        except BaseException:
            proc.terminate()
            proc.wait(timeout=10)
            raise

    senders = []
    try:
        process = start()
        with httpx.Client(base_url=base, timeout=5) as api:
            login = api.post('/api/v1/operators/login', json={"username": "uat-admin", "password": password})
            assert login.status_code == 200, login.text
            auth = {"Authorization": "Bearer " + login.json()["session_token"]}
            api.headers.update(auth)
            identities = []
            for name in ("uat-monitor-local", "uat-docker-protocol-local"):
                token = api.post('/api/v1/operators/bootstrap-tokens', headers=auth,
                                 json={"hostname": name})
                assert token.status_code == 201, token.text
                with httpx.Client(base_url=base) as enrollment:
                    result = enrollment.post('/api/v1/agents/enroll', json={
                        "hostname": name, "bootstrap_token": token.json()["token"]})
                assert result.status_code == 200, result.text
                identity = Identity(**{k: result.json()[k] for k in ("host_id", "agent_token")})
                path = tmp_path / f'{name}.json'
                save_identity(path, identity)
                assert load_identity(path) == identity
                identities.append(identity)
                sender = Sender(server_url=base, host_id=identity.host_id, agent_token=identity.agent_token)
                senders.append(sender)
                assert run_cycle(sender, telemetry_only=True)[0]
                # Assert immediately after this host's own cycle: with the
                # 1s/2s test thresholds, a heartbeat older than a second is
                # STALE/OFFLINE by design, and the next host's enrollment can
                # legitimately take longer than that on slow machines.
                host = api.get(f'/api/v1/hosts/{identity.host_id}').json()
                assert host['status'] == 'ONLINE', host
                assert host['latest_metrics']['memory_total_bytes'] > 0
                assert host['latest_metrics']['disk_total_bytes'] > 0
                assert host['last_telemetry_at']
            monitor, docker = identities
            assert monitor.host_id != docker.host_id
            denied = api.post('/api/v1/applications/deploy', headers=auth,
                              json={"host_id": monitor.host_id, "template_key": "nginx-demo"})
            assert denied.status_code == 403
            assert denied.json()['error']['code'] == 'DOCKER_NOT_AUTHORIZED'
            enabled = api.patch(f'/api/v1/hosts/{docker.host_id}', headers=auth, json={"docker_enabled": True})
            assert enabled.status_code == 200
            queued = api.post('/api/v1/applications/deploy', headers=auth,
                              json={"host_id": docker.host_id, "template_key": "nginx-demo"})
            assert queued.status_code == 202, queued.text
            for identity in identities:
                commands = api.post('/api/v1/agents/commands/poll', headers={
                    "Authorization": f'Bearer {identity.agent_token}', "X-Host-Id": identity.host_id}, json={})
                assert commands.status_code == 200, commands.text
                ids = [c['id'] for c in commands.json()['commands']]
                assert ids == ([] if identity == monitor else [queued.json()['operation_id']])
            # Real transport outage followed by API restart; identities/database survive.
            process.terminate()
            process.wait(timeout=10)
            assert not senders[0].send_heartbeat({})[0]
            time.sleep(2.1)
            process = start()
            assert api.get(f'/api/v1/hosts/{monitor.host_id}').json()['status'] == 'OFFLINE'
            assert run_cycle(senders[0], telemetry_only=True)[0]
            recovered = api.get(f'/api/v1/hosts/{monitor.host_id}').json()
            assert recovered['status'] == 'ONLINE'
            assert recovered['id'] == monitor.host_id
            assert api.get(f"/api/v1/operations/{queued.json()['operation_id']}").json()['host_id'] == docker.host_id
            if os.environ.get('NIMBUSOPS_UAT_BROWSER') == '1':
                check_dashboard(root, base, monitor.host_id, docker.host_id, tmp_path)
    finally:
        for sender in senders:
            sender.close()
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def check_dashboard(root, api_url, monitor_id, docker_id, output):
    """Optional actual Chromium check against Vite and this real isolated API."""
    from playwright.sync_api import sync_playwright

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    vite = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                             '--port', str(port), '--strictPort'], cwd=root / 'frontend',
                            env={**os.environ, 'API_PROXY_TARGET': api_url},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            assert vite.poll() is None, 'isolated Vite exited'
            try:
                if httpx.get(url).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError('Vite readiness timeout')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url)
                page.wait_for_load_state('networkidle')
                page.get_by_role('navigation', name='Primary').get_by_role(
                    'link', name='uat-monitor-local', exact=False).click()
                page.get_by_role('heading', name='uat-monitor-local', exact=True).wait_for()
                assert monitor_id in page.url
                page.get_by_role('tab', name='Monitoring', exact=True).click()
                page.get_by_text('Recent telemetry', exact=True).wait_for()
                page.get_by_role('navigation', name='Primary').get_by_role(
                    'link', name='uat-docker-protocol-local', exact=False).click()
                page.get_by_role('heading', name='uat-docker-protocol-local', exact=True).wait_for()
                assert docker_id in page.url
                page.screenshot(path=str(output / 'multihost-dashboard.png'), full_page=True)
            finally:
                browser.close()
    finally:
        vite.terminate()
        vite.wait(timeout=10)
