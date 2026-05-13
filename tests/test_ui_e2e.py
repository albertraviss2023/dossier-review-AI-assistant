from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - best effort polling
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for app health at {base_url}") from last_error


@pytest.fixture()
def live_server(tmp_path: Path):
    audit_file = tmp_path / "audit.jsonl"
    conversations_file = tmp_path / "conversations.json"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DOSSIER_AUDIT_LOG"] = str(audit_file)
    env["DOSSIER_CONVERSATIONS_STATE"] = str(conversations_file)
    env["DOSSIER_UPLOADED_DOSSIERS_DIR"] = str(uploads_dir)

    port = _free_port()
    process = subprocess.Popen(
        [
            r"C:\Users\alber\AppData\Local\Programs\Python\Python311\python.exe",
            "-m",
            "uvicorn",
            "dossier_review_ai_assistant.api:app",
            "--app-dir",
            "src",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=r"d:\projects\ai dossier assistant",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup guard
            process.kill()


def _require_playwright_enabled() -> None:
    if os.getenv("DOSSIER_ENABLE_PLAYWRIGHT_E2E", "0") != "1":
        pytest.skip("Playwright browser E2E is opt-in. Set DOSSIER_ENABLE_PLAYWRIGHT_E2E=1 to run it on a host that allows browser subprocesses.")


class _PlaywrightLaunchGuard:
    def __enter__(self):
        try:
            self._manager = sync_playwright()
            return self._manager.__enter__()
        except PermissionError as exc:
            pytest.skip(f"Playwright browser launch is blocked on this host: {exc}")
        except Exception as exc:
            message = str(exc)
            if "Access is denied" in message or "CreateFile" in message:
                pytest.skip(f"Playwright browser launch is blocked on this host: {message}")
            raise

    def __exit__(self, exc_type, exc, tb):
        if hasattr(self, "_manager"):
            return self._manager.__exit__(exc_type, exc, tb)
        return False


def _open_playwright():
    return _PlaywrightLaunchGuard()


def _login(page, base_url: str, username: str = "dachan", password: str = "123456") -> None:
    page.goto(f"{base_url}/review", wait_until="networkidle")
    if "/login" in page.url:
        page.locator("#username").fill(username)
        page.locator("#password").fill(password)
        page.locator("button[type='submit']").click()
        page.wait_for_url(f"{base_url}/review", timeout=30000)
    page.wait_for_selector("#composerShell", timeout=30000)
    page.wait_for_selector("#uploadBtn", timeout=30000)


def _select_first_dossier(page) -> None:
    page.locator("#activeDossierBadge").click()
    page.wait_for_selector("#dossierList > div", timeout=30000)
    page.locator("#dossierList > div").first.click()
    page.wait_for_timeout(500)


def test_review_upload_flow_reaches_ready_state(live_server: str):
    _require_playwright_enabled()

    sample_pdf = Path(r"d:\projects\ai dossier assistant\sample_dossiers\incoming_files\incoming_access_standard_submission.pdf")
    assert sample_pdf.exists()

    with _open_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _login(page, live_server)
        _select_first_dossier(page)

        body_text = page.locator("body").inner_text()
        assert "Dossier AI" in body_text
        assert "Context window 16,384 tokens · compaction at 98%" in body_text

        file_input = page.locator("#hiddenUploadInput")
        file_input.set_input_files(str(sample_pdf))

        page.wait_for_timeout(1000)
        page.wait_for_selector("text=File uploaded successfully", timeout=120000)

        body_text = page.locator("body").inner_text()
        assert "[object Object]" not in body_text
        assert "File uploaded successfully" in body_text

        browser.close()


def test_review_upload_button_accepts_attachment_selection(live_server: str):
    _require_playwright_enabled()

    sample_pdf = Path(r"d:\projects\ai dossier assistant\sample_dossiers\incoming_files\incoming_access_standard_submission.pdf")
    assert sample_pdf.exists()

    with _open_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _login(page, live_server)
        _select_first_dossier(page)

        with page.expect_file_chooser() as chooser_info:
            page.locator("#uploadBtn").click()
        file_chooser = chooser_info.value
        file_chooser.set_files(str(sample_pdf))

        page.wait_for_selector("text=File uploaded successfully", timeout=120000)
        body_text = page.locator("body").inner_text()
        assert "File uploaded successfully" in body_text

        browser.close()


def test_review_composer_accepts_click_focus(live_server: str):
    _require_playwright_enabled()

    with _open_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _login(page, live_server)

        page.locator("#composerShell").click()
        page.locator("#chatInput").fill("Hello reviewer workflow")
        assert page.locator("#chatInput").input_value() == "Hello reviewer workflow"

        browser.close()


def test_review_voice_input_populates_query_and_submits(live_server: str):
    _require_playwright_enabled()

    with _open_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            """
            (() => {
              class MockSpeechRecognition {
                constructor() {
                  window.__mockRecognition = this;
                  this.onstart = null;
                  this.onresult = null;
                  this.onerror = null;
                  this.onend = null;
                }
                start() {
                  if (this.onstart) this.onstart();
                }
                stop() {
                  if (this.onend) this.onend();
                }
                emitTranscript(text) {
                  if (!this.onresult) return;
                  this.onresult({
                    results: [[{ transcript: text }]],
                  });
                }
              }
              window.SpeechRecognition = MockSpeechRecognition;
              window.webkitSpeechRecognition = MockSpeechRecognition;
            })();
            """
        )
        _login(page, live_server)

        page.locator("#voiceBtn").click()
        page.evaluate("window.__mockRecognition.emitTranscript('Summarize this dossier')")
        page.locator("#voiceBtn").click()
        page.wait_for_timeout(300)
        assert page.locator("#chatInput").input_value() == "Summarize this dossier"

        browser.close()
