"""Cookie boundary tests; isolated fixture database, no real enrollment/Docker."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.core.security import hash_operator_password
from backend.app.models import Operator, OperatorSession


@pytest.fixture
def accounts(db_session):
    for name, role in (("admin-test", "ADMIN"), ("reader-test", "VIEWER")):
        db_session.add(Operator(username=name, role=role, password_hash=hash_operator_password("test-only-password")))
    db_session.commit()


@pytest.fixture(autouse=True)
def browser_settings(monkeypatch):
    from backend.app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'session_cookie_secure', False)
    monkeypatch.setattr(get_settings(), 'browser_origins', 'http://testserver')


def csrf(client):
    r = client.get('/api/v1/operators/session/csrf')
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json()['csrf_token'], 'Origin': 'http://testserver'}


def login(client, username='reader-test'):
    return client.post('/api/v1/operators/session/login', json={'username': username, 'password': 'test-only-password'}, headers=csrf(client))


@pytest.mark.parametrize('path', ['/hosts', '/templates', '/applications', '/operations'])
def test_anonymous_operational_reads_rejected(client, path):
    assert client.get('/api/v1' + path).status_code == 401


def test_cookie_session_restore_logout_and_csrf(client, accounts):
    r = login(client)
    assert r.status_code == 200
    assert 'session_token' not in r.json()
    assert 'HttpOnly' in r.headers['set-cookie']
    assert 'SameSite=strict' in r.headers['set-cookie']
    assert client.get('/api/v1/operators/me').json()['role'] == 'VIEWER'
    assert client.get('/api/v1/hosts').status_code == 200
    assert client.post('/api/v1/operators/session/logout').status_code == 403
    assert client.post('/api/v1/operators/session/logout', headers=csrf(client)).status_code == 200
    assert client.get('/api/v1/hosts').status_code == 401


def test_viewer_denied_privileged_operations(client, accounts):
    assert login(client).status_code == 200
    h = csrf(client)
    for method, path, body in [('POST','/applications/deploy',{'host_id':'missing','template_key':'nginx'}), ('PATCH','/hosts/missing',{'docker_enabled':True}), ('DELETE','/hosts/missing',None), ('POST','/operators/bootstrap-tokens',{'hostname':'not-real'})]:
        assert client.request(method, '/api/v1'+path, json=body, headers=h).status_code == 403


def test_admin_requires_csrf_even_with_bearer_header(client, accounts):
    assert login(client, 'admin-test').status_code == 200
    assert client.patch('/api/v1/hosts/missing', json={'docker_enabled':True}, headers={'Authorization':'Bearer invalid'}).status_code == 403
    assert client.patch('/api/v1/hosts/missing', json={'docker_enabled':True}, headers=csrf(client)).status_code == 404


def test_expired_cookie_rejected(client, accounts, db_session):
    assert login(client).status_code == 200
    s = db_session.scalar(select(OperatorSession))
    s.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get('/api/v1/operators/me').status_code == 401


def test_login_requires_csrf_and_rejects_foreign_origin(client, accounts):
    data={'username':'reader-test','password':'test-only-password'}
    assert client.post('/api/v1/operators/session/login',json=data).status_code == 403
    h=csrf(client)
    h['Origin']='https://foreign.invalid'
    assert client.post('/api/v1/operators/session/login',json=data,headers=h).status_code == 403


def test_invalid_credentials_and_rate_limit(client, accounts):
    h=csrf(client)
    statuses=[client.post('/api/v1/operators/session/login', json={'username':'rate-test','password':'wrong'},headers=h).status_code for _ in range(6)]
    assert statuses == [401]*5+[429]


def test_password_hash_uses_library_and_accepts_legacy():
    import hashlib
    from backend.app.core.security import verify_operator_password
    hashed = hash_operator_password('arbitrary-test-password')
    assert hashed.startswith('$argon2id$')
    assert verify_operator_password('arbitrary-test-password', hashed)
    assert not verify_operator_password('wrong', hashed)
    salt = b'legacy-test-salt'
    dk = hashlib.pbkdf2_hmac('sha256', b'legacy-password', salt, 240000)
    legacy = f'pbkdf2$240000${salt.hex()}${dk.hex()}'
    assert verify_operator_password('legacy-password', legacy)


def test_legacy_logout_cannot_bypass_cookie_csrf(client, accounts):
    assert login(client).status_code == 200
    assert client.post('/api/v1/operators/logout').status_code == 403


def test_agent_boundary_and_telemetry_preserved(client, enrolled_host, accounts):
    host_id, token = enrolled_host
    h={'X-Host-Id':host_id,'Authorization':f'Bearer {token}'}
    assert client.post('/api/v1/agents/heartbeat',json={'agent_version':'test'},headers=h).status_code == 200
    payload={'recorded_at':datetime.now(timezone.utc).isoformat(),'cpu_percent':12,'memory_used_bytes':1,'memory_total_bytes':2,'disk_used_bytes':1,'disk_total_bytes':2}
    assert client.post('/api/v1/agents/telemetry',json=payload,headers=h).status_code == 200
    assert client.get('/api/v1/hosts',headers=h).status_code == 401
    assert login(client).status_code == 200
    assert client.post('/api/v1/agents/commands/poll',headers={'X-Host-Id':host_id}).status_code == 401
    assert client.post('/api/v1/agents/commands/poll',headers=h).status_code == 200
    detail=client.get(f'/api/v1/hosts/{host_id}').json()
    assert detail['id']==host_id and detail['latest_metrics']['cpu_percent']==12
    assert 'token' not in str(detail).lower()
    assert client.get('/api/v1/hosts').headers.get('cache-control') == 'no-store'


def test_cookie_precedence_and_captured_cookie_revocation(client, accounts, db_session):
    bearer=client.post('/api/v1/operators/login',json={'username':'admin-test','password':'test-only-password'}).json()['session_token']
    assert login(client).status_code==200
    cookie=client.cookies.get('nimbusops_session')
    h={**csrf(client),'Authorization':'Bearer '+bearer}
    assert client.patch('/api/v1/hosts/missing',json={'docker_enabled':True},headers=h).status_code==403
    assert client.post('/api/v1/operators/session/logout',headers=csrf(client)).status_code==200
    client.cookies.set('nimbusops_session',cookie,path='/api/v1')
    assert client.get('/api/v1/hosts',headers={'Authorization':'Bearer '+bearer}).status_code==401
