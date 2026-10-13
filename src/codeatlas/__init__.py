"""Typed client for the public CodeAtlas API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

__all__ = [
    "DEFAULT_BASE_URL",
    "CodeAtlas",
    "CodeAtlasError",
    "Health",
    "Service",
    "ServiceList",
]

__version__ = "0.1.0"
DEFAULT_BASE_URL = "https://codeatlas.com.br/api/v1"


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
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.services = _Services(self)

    def health(self) -> Health:
        body = self._request("/health")
        return Health(status=body["status"], service=body["service"], version=body["version"])

    def _request(self, path: str, query: Optional[Dict[str, str]] = None) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            headers={"accept": "application/json", "user-agent": f"codeatlas-python/{__version__}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as http_error:
            try:
                err = json.loads(http_error.read().decode("utf-8")).get("error", {})
            except (ValueError, AttributeError):
                err = {}
            raise CodeAtlasError(
                http_error.code,
                err.get("code", "unknown_error"),
                err.get("message", f"HTTP {http_error.code}"),
                err.get("hint", ""),
            ) from None
