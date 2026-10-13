"""Write API against a local server that follows the wire contract of
POST /oauth2/register, POST /oauth2/token and POST /api/v1/contact-requests.
The read API is tested live in test_live.py."""

import base64
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import codeatlas
from codeatlas import CodeAtlas, CodeAtlasError, Credentials

calls = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0))).decode()
        calls.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path == "/oauth2/register":
            return self._reply(
                201, {"client_id": "ca_1", "client_secret": "cas_1", "client_name": json.loads(body)["client_name"]}
            )
        if self.path == "/oauth2/token":
            good = base64.b64encode(b"ca_1:cas_1").decode()
            form = urllib.parse.parse_qs(body)
            if self.headers.get("authorization") != f"Basic {good}" or form.get("grant_type") != ["client_credentials"]:
                return self._reply(401, {"error": "invalid_client", "error_description": "bad secret"})
            return self._reply(200, {"access_token": "tok", "expires_in": 3600, "token_type": "Bearer"})
        if self.path == "/api/v1/contact-requests":
            if not json.loads(body).get("email"):
                return self._reply(400, {"error": {"code": "bad_request", "message": "email", "hint": "Use a valid email."}})
            return self._reply(
                201, {"data": {"id": "cr_1", "status": "received", "delivery": "stored", "created_at": "2026-01-01T00:00:00Z"}}
            )
        self._reply(404, {"error": {"code": "not_found", "message": "x", "hint": "y"}})


@pytest.fixture()
def origin(monkeypatch):
    calls.clear()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    # OAuth calls go to the production origin: route them to the local server.
    monkeypatch.setattr(codeatlas, "_ORIGIN", url)
    yield url
    server.shutdown()


def test_register_then_create_reuses_token(origin):
    creds = CodeAtlas.register("my-agent")
    assert creds == Credentials("ca_1", "cas_1")
    client = CodeAtlas(base_url=origin + "/api/v1", credentials=creds)
    created = client.contact_requests.create(
        "Ana Souza", "ana@example.com", "Preciso de um diagnóstico.", idempotency_key="key-12345678"
    )
    client.contact_requests.create("Ana Souza", "ana@example.com", "Preciso de um diagnóstico.")
    assert (created.id, created.status) == ("cr_1", "received")
    assert [c[0] for c in calls].count("/oauth2/token") == 1
    post = next(c for c in calls if c[0] == "/api/v1/contact-requests")
    assert post[1]["idempotency-key"] == "key-12345678"
    token_form = urllib.parse.parse_qs(next(c for c in calls if c[0] == "/oauth2/token")[2])
    assert token_form["resource"] == [origin + "/api/v1"]


def test_create_without_credentials_fails_before_any_request(origin):
    with pytest.raises(CodeAtlasError) as info:
        CodeAtlas(base_url=origin + "/api/v1").contact_requests.create("Ana", "a@b.co", "mensagem longa ok")
    assert info.value.code == "unauthorized"
    assert calls == []


def test_oauth_and_api_errors(origin):
    bad = CodeAtlas(base_url=origin + "/api/v1", credentials=Credentials("ca_1", "wrong"))
    with pytest.raises(CodeAtlasError) as oauth:
        bad.contact_requests.create("Ana", "a@b.co", "mensagem longa ok")
    assert (oauth.value.status, oauth.value.code) == (401, "invalid_client")

    ok = CodeAtlas(base_url=origin + "/api/v1", credentials=Credentials("ca_1", "cas_1"))
    with pytest.raises(CodeAtlasError) as api:
        ok.contact_requests.create("Ana", "", "mensagem longa ok")
    assert (api.value.status, api.value.code, api.value.hint) == (400, "bad_request", "Use a valid email.")
