"""Typed client for the public CodeAtlas API."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

__all__ = [
    "DEFAULT_BASE_URL",
    "SANDBOX_BASE_URL",
    "CodeAtlas",
    "CodeAtlasError",
    "BatchResult",
    "ContactRequest",
    "Credentials",
    "ExportJob",
    "Health",
    "Service",
    "ServiceList",
]

__version__ = "0.1.0"
DEFAULT_BASE_URL = "https://codeatlas.com.br/api/v1"
# Same API with no side effects: writes are validated but nothing is stored or sent.
SANDBOX_BASE_URL = "https://codeatlas.com.br/api/sandbox/v1"
_ORIGIN = "https://codeatlas.com.br"


class CodeAtlasError(Exception):
    """Non-2xx response; mirrors the API error envelope."""

    def __init__(self, status: int, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        base = f"{self.status} {self.code}: {self.message}"
        return f"{base} ({self.hint})" if self.hint else base


@dataclass(frozen=True)
class Service:
    slug: str
    name: str
    description: str
    service_type: str
    url: str
    capabilities: List[str]
    delivery_timeline: str

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Service":
        return cls(
            slug=raw["slug"],
            name=raw["name"],
            description=raw["description"],
            service_type=raw["serviceType"],
            url=raw["url"],
            capabilities=list(raw["capabilities"]),
            delivery_timeline=raw["deliveryTimeline"],
        )


@dataclass(frozen=True)
class ServiceList:
    data: List[Service]
    count: int
    """Total number of services, not the page size."""
    next_cursor: Optional[str]
    """Pass as `cursor` to get the next page. None on the last page."""


@dataclass(frozen=True)
class Health:
    status: str
    service: str
    version: str


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class ContactRequest:
    id: str
    status: str
    delivery: str
    """"delivered" or "stored" in production, "sandbox" on the sandbox API."""
    created_at: str


@dataclass(frozen=True)
class BatchResult:
    slug: Optional[str]
    status: int
    """HTTP-style status of this item: 200, 404 or 400."""
    data: Optional[Service] = None
    error: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class ExportJob:
    id: str
    status: str
    """"queued", "running" or "succeeded"."""
    format: str
    download_url: Optional[str]
    """Set when status is "succeeded"."""
    created_at: str
    expires_at: str
    """Jobs and files are kept for 24 hours."""

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ExportJob":
        return cls(
            id=raw["id"],
            status=raw["status"],
            format=raw["format"],
            download_url=raw["download_url"],
            created_at=raw["created_at"],
            expires_at=raw["expires_at"],
        )


class _Exports:
    def __init__(self, client: "CodeAtlas") -> None:
        self._client = client

    def create(self, format: str, idempotency_key: Optional[str] = None) -> ExportJob:
        """Start an export job: format is "jsonl", "csv" or "md" (10 per hour per client). Requires credentials."""
        body = self._client._send(
            "POST",
            self._client.base_url + "/exports",
            json.dumps({"format": format}).encode(),
            self._client._auth_headers(idempotency_key),
        )
        return ExportJob.from_dict(body["data"])

    def get(self, export_id: str) -> ExportJob:
        body = self._client._send(
            "GET",
            f"{self._client.base_url}/exports/{urllib.parse.quote(export_id, safe='')}",
            headers=self._client._auth_headers(),
        )
        return ExportJob.from_dict(body["data"])

    def wait(self, export_id: str, interval: float = 1.0, timeout: float = 60.0) -> ExportJob:
        """Poll until the job has succeeded. Raises TimeoutError after `timeout` seconds."""
        deadline = time.time() + timeout
        while True:
            job = self.get(export_id)
            if job.status == "succeeded":
                return job
            if time.time() >= deadline:
                raise TimeoutError(f"Export {export_id} is still {job.status} after {timeout}s")
            time.sleep(interval)

    def download(self, export_id: str) -> str:
        """The file of a succeeded job, as text."""
        return self._client._send_text(
            "GET",
            f"{self._client.base_url}/exports/{urllib.parse.quote(export_id, safe='')}/download",
            headers=self._client._auth_headers(),
            accept="*/*",
        )


class _ContactRequests:
    def __init__(self, client: "CodeAtlas") -> None:
        self._client = client

    def create(
        self,
        name: str,
        email: str,
        message: str,
        company: Optional[str] = None,
        locale: Optional[str] = None,
        service_slug: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> ContactRequest:
        """Send a contact request to the CodeAtlas team. Requires credentials.

        Pass idempotency_key (8 to 128 printable ASCII characters) to make retries safe.
        """
        payload: Dict[str, Any] = {"name": name, "email": email, "message": message}
        for key, value in (("company", company), ("locale", locale), ("service_slug", service_slug)):
            if value is not None:
                payload[key] = value
        body = self._client._send(
            "POST",
            self._client.base_url + "/contact-requests",
            json.dumps(payload).encode(),
            self._client._auth_headers(idempotency_key),
        )
        data = body["data"]
        return ContactRequest(
            id=data["id"], status=data["status"], delivery=data["delivery"], created_at=data["created_at"]
        )


class _Services:
    def __init__(self, client: "CodeAtlas") -> None:
        self._client = client

    def list(self, limit: Optional[int] = None, cursor: Optional[str] = None) -> ServiceList:
        """One page of the service catalog (limit 1 to 100, default 20)."""
        query: Dict[str, str] = {}
        if limit is not None:
            query["limit"] = str(limit)
        if cursor is not None:
            query["cursor"] = cursor
        body = self._client._request("/services", query)
        return ServiceList(
            data=[Service.from_dict(item) for item in body["data"]],
            count=body["count"],
            next_cursor=body["next_cursor"],
        )

    def get(self, slug: str) -> Service:
        """One service by slug. Raises CodeAtlasError (not_found) when missing."""
        body = self._client._request("/services/" + urllib.parse.quote(slug, safe=""))
        return Service.from_dict(body["data"])

    def iterate(self, limit: Optional[int] = None) -> Iterator[Service]:
        """Every service, following next_cursor."""
        cursor: Optional[str] = None
        while True:
            page = self.list(limit=limit, cursor=cursor)
            yield from page.data
            if page.next_cursor is None:
                return
            cursor = page.next_cursor

    def batch(self, slugs: List[str]) -> List[BatchResult]:
        """Up to 50 slugs in one call. Unknown slugs come back as 404 items, not as an exception."""
        body = self._client._send(
            "POST",
            self._client.base_url + "/services/batch",
            json.dumps({"slugs": slugs}).encode(),
            {"content-type": "application/json"},
        )
        return [
            BatchResult(
                slug=item["slug"],
                status=item["status"],
                data=Service.from_dict(item["data"]) if "data" in item else None,
                error=item.get("error"),
            )
            for item in body["results"]
        ]

    def search(self, query: str) -> List[Service]:
        """Case-insensitive match on slug, name, description, type and capabilities.

        The API has no search endpoint: this filters the full catalog on the client.
        """
        terms = query.lower().split()
        results: List[Service] = []
        for service in self.iterate(limit=100):
            haystack = "\n".join(
                [service.slug, service.name, service.description, service.service_type]
                + service.capabilities
            ).lower()
            if all(term in haystack for term in terms):
                results.append(service)
        return results


class CodeAtlas:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        credentials: Optional[Credentials] = None,
    ) -> None:
        """credentials: OAuth client credentials, needed for writes. Get them with CodeAtlas.register()."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.services = _Services(self)
        self.contact_requests = _ContactRequests(self)
        self.exports = _Exports(self)
        self._credentials = credentials
        self._token: Optional[Tuple[str, float]] = None

    @classmethod
    def register(cls, client_name: str, timeout: float = 15.0) -> Credentials:
        """Register a new OAuth client (RFC 7591). The secret is shown once: store it."""
        body = cls(timeout=timeout)._send(
            "POST",
            _ORIGIN + "/oauth2/register",
            json.dumps({"client_name": client_name, "grant_types": ["client_credentials"]}).encode(),
            {"content-type": "application/json"},
        )
        return Credentials(client_id=body["client_id"], client_secret=body["client_secret"])

    def _auth_headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {"content-type": "application/json", "authorization": f"Bearer {self._access_token()}"}
        if idempotency_key:
            headers["idempotency-key"] = idempotency_key
        return headers

    def _access_token(self) -> str:
        if self._credentials is None:
            raise CodeAtlasError(
                401,
                "unauthorized",
                "This call needs OAuth credentials.",
                "Create them with CodeAtlas.register(name) and pass credentials= to CodeAtlas().",
            )
        if self._token and self._token[1] > time.time() + 30:
            return self._token[0]
        basic = base64.b64encode(
            f"{self._credentials.client_id}:{self._credentials.client_secret}".encode()
        ).decode()
        # The token audience is the API base URL (production or sandbox).
        form = urllib.parse.urlencode({"grant_type": "client_credentials", "resource": self.base_url})
        token = self._send(
            "POST",
            _ORIGIN + "/oauth2/token",
            form.encode(),
            {"content-type": "application/x-www-form-urlencoded", "authorization": f"Basic {basic}"},
        )
        self._token = (token["access_token"], time.time() + token["expires_in"])
        return token["access_token"]

    def health(self) -> Health:
        body = self._request("/health")
        return Health(status=body["status"], service=body["service"], version=body["version"])

    def _request(self, path: str, query: Optional[Dict[str, str]] = None) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        return self._send("GET", url)

    def _send_text(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        accept: str = "application/json",
    ) -> str:
        """One request path for everything: returns the text, raises CodeAtlasError on non-2xx."""
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"accept": accept, "user-agent": f"codeatlas-python/{__version__}", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as http_error:
            try:
                raw = json.loads(http_error.read().decode("utf-8"))
            except ValueError:
                raw = {}
            raise _to_error(http_error.code, raw) from None

    def _send(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        text = self._send_text(method, url, data, headers)
        return json.loads(text) if text else None


def _to_error(status: int, raw: Any) -> CodeAtlasError:
    """Understands both the API error envelope and OAuth errors (RFC 6749 / 7591)."""
    err = raw.get("error") if isinstance(raw, dict) else None
    if isinstance(err, str):
        return CodeAtlasError(status, err, raw.get("error_description", err), "")
    err = err if isinstance(err, dict) else {}
    return CodeAtlasError(
        status,
        err.get("code", "unknown_error"),
        err.get("message", f"HTTP {status}"),
        err.get("hint", ""),
    )
