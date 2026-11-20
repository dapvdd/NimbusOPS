"""Local browser acceptance. Reads credentials privately; reports booleans only."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main() -> None:
    home = Path(os.environ['NIMBUSOPS_AUTH_PREVIEW_HOME'])
    ui_base = os.environ.get('NIMBUSOPS_PREVIEW_UI_BASE_URL', 'http://127.0.0.1:18421')
    admin_file = Path(os.environ['NIMBUSOPS_AUTH_ADMIN_CREDENTIAL_FILE'])
    admin = json.loads(admin_file.read_text(encoding='utf-8-sig'))
    viewer = json.loads((home/'viewer-private.json').read_text())
    report = {'checks': {}, 'page_errors': [], 'credential_log_leaks': False}
    secrets = [admin['password'], viewer['password']]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for label, credentials in [('ADMIN', admin), ('VIEWER', viewer)]:
                context = browser.new_context()
                page = context.new_page()
                page.on('pageerror', lambda e: report['page_errors'].append(type(e).__name__))
                def console(message):
                    if any(secret in message.text for secret in secrets):
                        report['credential_log_leaks'] = True
                page.on('console', console)
                page.goto(ui_base + '/servers')
                page.wait_for_load_state('networkidle')
                expect(page.get_by_role('heading',name='Sign in to NimbusOps')).to_be_visible()
                page.get_by_label('Username',exact=True).fill(credentials['username'])
                page.get_by_label('Password',exact=True).fill(credentials['password'])
                page.get_by_role('button',name='Sign in',exact=True).click()
                expect(page.get_by_text(f"{credentials['username']} · {label}",exact=True)).to_be_visible()
                page.goto(ui_base + '/servers')
                page.wait_for_load_state('networkidle')
                expect(page.get_by_text(f"{credentials['username']} · {label}",exact=True)).to_be_visible()
                if label == 'ADMIN':
                    expect(page.get_by_role('button',name='Add Server',exact=True)).to_be_visible()
                else:
                    expect(page.get_by_role('button',name='Add Server',exact=True)).to_have_count(0)
                    result=page.evaluate("""async () => {
                      const c=await (await fetch('/api/v1/operators/session/csrf')).json();
                      return (await fetch('/api/v1/hosts/nonexistent',{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':c.csrf_token},body:JSON.stringify({docker_enabled:true})})).status;
                    }""")
                    assert result == 403
                    page.goto(ui_base + '/activity')
                    expect(page.get_by_role('button',name='Log out')).to_be_visible()
                cookies=context.cookies()
                session=next(c for c in cookies if c['name']=='nimbusops_session')
                assert session['httpOnly'] and session['sameSite']=='Strict'
                assert page.evaluate("localStorage.getItem('operatorSessionToken')") is None
                page.get_by_role('button',name='Log out').click()
                expect(page.get_by_role('heading',name='Sign in to NimbusOps')).to_be_visible()
                page.reload()
                expect(page.get_by_role('heading',name='Sign in to NimbusOps')).to_be_visible()
                report['checks'][label+'_login_refresh_role_logout']=True
                context.close()
        finally:
            browser.close()
    assert not report['page_errors'] and not report['credential_log_leaks']
    (home/'browser-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
