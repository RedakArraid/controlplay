"""
Tests E2E dans un navigateur réel (Chromium via Playwright).

Marqueur pytest : ``browser`` (``pytest -m browser``).

Prérequis ::
    pip install -r requirements-e2e.txt
    playwright install chromium
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import expect, sync_playwright  # noqa: E402

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
E2E_PORT = int(os.environ.get("E2E_PORT", "9876"))
BASE = f"http://127.0.0.1:{E2E_PORT}"

ADMIN_USER = (os.environ.get("ADMIN_USERNAME") or "").strip() or "admin@test.com"
ADMIN_PASS = (os.environ.get("ADMIN_PASSWORD") or "").strip() or "testpass123"


def _fill_login_form(page, username: str, password: str) -> None:
    page.locator('input[name="identifier"]').fill(username)
    page.locator('input[name="password"]').fill(password)


@pytest.fixture(scope="module")
def e2e_server():
    env = os.environ.copy()
    env.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest")
    env["ADMIN_USERNAME"] = "admin@test.com"
    env["ADMIN_PASSWORD"] = "testpass123"
    env["DATABASE_URL"] = "sqlite://"
    env.setdefault("AUTO_CREATE_SCHEMA", "false")
    env["E2E_PORT"] = str(E2E_PORT)

    proc = subprocess.Popen(
        [sys.executable, os.path.join(os.path.dirname(__file__), "e2e_server.py")],
        cwd=APP_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(f"{BASE}/health", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            err = proc.stderr.read() if proc.stderr else b""
            proc.terminate()
            pytest.fail(f"Serveur E2E non joignable sur {BASE}: {err.decode()[:800]}")
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        yield br
        br.close()


@pytest.fixture
def page(browser, e2e_server):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.set_default_timeout(15_000)
    yield pg
    ctx.close()


pytestmark = pytest.mark.browser


@pytest.mark.browser
def test_admin_redirects_to_login_in_browser(page, e2e_server):
    page.goto(f"{e2e_server}/admin")
    expect(page).to_have_url(re.compile(r".*/login\?next=.*"))


@pytest.mark.browser
def test_super_admin_redirects_to_login_in_browser(page, e2e_server):
    page.goto(f"{e2e_server}/super-admin")
    expect(page).to_have_url(re.compile(r".*/login\?next=.*"))


@pytest.mark.browser
def test_login_page_visible(page, e2e_server):
    page.goto(f"{e2e_server}/login")
    expect(page.get_by_role("heading", name=re.compile("Connexion", re.I))).to_be_visible()
    expect(page.get_by_role("link", name=re.compile("ControlPlay", re.I))).to_be_visible()
    expect(
        page.get_by_text(
            re.compile(r"Saisissez l.email ou le téléphone", re.I),
        )
    ).to_be_visible()


@pytest.mark.browser
def test_login_then_admin_dashboard(page, e2e_server):
    page.goto(f"{e2e_server}/login?next=/admin")
    _fill_login_form(page, ADMIN_USER, ADMIN_PASS)
    page.get_by_role("button", name="Se connecter").click()
    expect(page).to_have_url(f"{e2e_server}/admin")


@pytest.mark.browser
def test_login_then_super_admin_hub(page, e2e_server):
    page.goto(f"{e2e_server}/login?next=/super-admin")
    _fill_login_form(page, ADMIN_USER, ADMIN_PASS)
    page.get_by_role("button", name="Se connecter").click()
    expect(page).to_have_url(f"{e2e_server}/super-admin")
    expect(page.get_by_role("heading", name="Espace plateforme")).to_be_visible()


@pytest.mark.browser
def test_logout_clears_session_in_browser(page, e2e_server):
    page.goto(f"{e2e_server}/login?next=/admin")
    _fill_login_form(page, ADMIN_USER, ADMIN_PASS)
    page.get_by_role("button", name="Se connecter").click()
    expect(page).to_have_url(f"{e2e_server}/admin")

    page.goto(f"{e2e_server}/logout")
    expect(page).to_have_url(f"{e2e_server}/login")

    page.goto(f"{e2e_server}/admin")
    expect(page).to_have_url(re.compile(r".*/login\?next=.*"))


@pytest.mark.browser
def test_navigateur_page_login_avec_next_admin(page, e2e_server):
    """URL /login?next=%2Fadmin puis formulaire → panel /admin."""
    page.goto(f"{e2e_server}/login?next={urllib.parse.quote('/admin')}")
    expect(page.get_by_role("heading", name=re.compile("Connexion", re.I))).to_be_visible()
    _fill_login_form(page, ADMIN_USER, ADMIN_PASS)
    page.get_by_role("button", name="Se connecter").click()
    expect(page).to_have_url(f"{e2e_server}/admin")


@pytest.mark.browser
def test_navigateur_page_login_avec_next_super_admin(page, e2e_server):
    """URL /login?next=%2Fsuper-admin puis formulaire → hub super admin."""
    page.goto(f"{e2e_server}/login?next={urllib.parse.quote('/super-admin')}")
    _fill_login_form(page, ADMIN_USER, ADMIN_PASS)
    page.get_by_role("button", name="Se connecter").click()
    expect(page).to_have_url(f"{e2e_server}/super-admin")
    expect(page.get_by_role("heading", name="Espace plateforme")).to_be_visible()
