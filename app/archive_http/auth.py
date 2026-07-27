from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests

from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.errors import ArchiveHttpAuthError


@dataclass
class ArchiveHttpAuth:
    config: ArchiveHttpConfig
    token: str | None = None
    jsessionid: str | None = None
    session: requests.Session = field(default_factory=requests.Session)
    _login_attempted: bool = False

    @classmethod
    def from_config(cls, config: ArchiveHttpConfig) -> "ArchiveHttpAuth":
        return cls(
            config=config,
            token=config.auth_token,
            jsessionid=config.jsessionid or config.auth_token,
        )

    def ensure_authenticated(self) -> None:
        if self.token or self.jsessionid:
            return
        if not self.config.username or not self.config.password:
            return
        self.refresh()

    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.config.base_url}/history/customizedquery",
        }
        if self.token:
            headers["Authorization"] = self.token
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def refresh(self) -> None:
        if not self.config.username or not self.config.password or not self.config.login_url:
            raise ArchiveHttpAuthError("Archive HTTP login requires username, password and login_url.")

        self._login_attempted = True
        self.session = requests.Session()
        try:
            login_page = self.session.get(
                self.config.login_url,
                timeout=self.config.timeout_seconds,
                headers={"User-Agent": "diagnosis-agent/0.1"},
            )
            login_page.raise_for_status()
            form = _parse_login_form(login_page.text)
            action_url = urljoin(login_page.url, form.action or self.config.login_url)
            payload = dict(form.inputs)
            payload.update(
                {
                    "username": self.config.username,
                    "password": self.config.password,
                }
            )
            response = self.session.post(
                action_url,
                data=payload,
                timeout=self.config.timeout_seconds,
                allow_redirects=True,
                headers={
                    "User-Agent": "diagnosis-agent/0.1",
                    "Referer": login_page.url,
                },
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ArchiveHttpAuthError(f"Archive HTTP login request failed: {exc}") from exc

        self._sync_from_session()
        if not self.jsessionid and _looks_like_login_page(response.text):
            raise ArchiveHttpAuthError("Archive HTTP login did not leave CAS login page.")
        if not self.jsessionid:
            raise ArchiveHttpAuthError("Archive HTTP login did not return JSESSIONID.")

    def invalidate(self) -> None:
        """Discard a failed dynamic login so the next request can retry CAS."""
        if not self.config.username or not self.config.password:
            return
        self.token = None
        self.jsessionid = None
        self._login_attempted = False
        self.session = requests.Session()

    def _sync_from_session(self) -> None:
        cookies = self._target_cookies()
        self.jsessionid = cookies.get("JSESSIONID") or self.jsessionid
        if self._login_attempted and self.jsessionid:
            self.token = self.jsessionid
        elif not self.token and self.jsessionid:
            self.token = self.jsessionid

    def _cookie_header(self) -> str:
        cookies = self._target_cookies()
        if self.jsessionid:
            cookies.setdefault("JSESSIONID", self.jsessionid)
        return "; ".join(f"{key}={value}" for key, value in cookies.items())

    def _target_cookies(self) -> dict[str, str]:
        host = urlparse(self.config.base_url).hostname or ""
        cookies: dict[str, str] = {}
        for cookie in self.session.cookies:
            domain = cookie.domain.lstrip(".")
            if domain == host or host.endswith(f".{domain}"):
                cookies[cookie.name] = cookie.value
        return cookies


@dataclass(frozen=True)
class LoginForm:
    action: str | None
    inputs: dict[str, str]


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_form = False
        self.form_depth = 0
        self.action: str | None = None
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value for key, value in attrs}
        if tag.lower() == "form":
            if self.action is None:
                self.in_form = True
                self.form_depth = 1
                self.action = attrs_map.get("action")
            elif self.in_form:
                self.form_depth += 1
        elif tag.lower() == "input" and self.in_form:
            name = attrs_map.get("name")
            if name:
                self.inputs[name] = attrs_map.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self.in_form:
            self.form_depth -= 1
            if self.form_depth <= 0:
                self.in_form = False


def _parse_login_form(html: str) -> LoginForm:
    parser = _LoginFormParser()
    parser.feed(html)
    return LoginForm(action=parser.action, inputs=parser.inputs)


def _looks_like_login_page(html: str) -> bool:
    lowered = html.lower()
    return "name=\"password\"" in lowered or "cas" in lowered and "login" in lowered
