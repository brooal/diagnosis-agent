from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.archive_http.auth import ArchiveHttpAuth, _parse_login_form
from app.archive_http.config import ArchiveHttpConfig


def test_parse_cas_login_form_hidden_fields() -> None:
    form = _parse_login_form(
        """
        <html><body>
          <form action="/cas/login?service=x" method="post">
            <input type="hidden" name="execution" value="e1s1" />
            <input type="hidden" name="_eventId" value="submit" />
            <input name="username" />
            <input name="password" />
          </form>
        </body></html>
        """
    )

    assert form.action == "/cas/login?service=x"
    assert form.inputs["execution"] == "e1s1"
    assert form.inputs["_eventId"] == "submit"


def test_headers_use_manual_token_without_login() -> None:
    auth = ArchiveHttpAuth.from_config(
        ArchiveHttpConfig(
            auth_token="token-1",
            jsessionid="session-1",
        )
    )

    headers = auth.headers()

    assert headers["Authorization"] == "token-1"
    assert headers["Cookie"] == "JSESSIONID=session-1"


def test_target_cookie_prefers_hlsts_domain() -> None:
    auth = ArchiveHttpAuth.from_config(
        ArchiveHttpConfig(base_url="http://202.38.77.8")
    )
    auth.session.cookies.set("JSESSIONID", "cas-session", domain="nsrloa.ustc.edu.cn", path="/cas")
    auth.session.cookies.set("JSESSIONID", "hls-session", domain="202.38.77.8", path="/")
    auth._login_attempted = True
    auth._sync_from_session()

    assert auth.jsessionid == "hls-session"
    assert auth.headers()["Authorization"] == "hls-session"
    assert auth.headers()["Cookie"] == "JSESSIONID=hls-session"
