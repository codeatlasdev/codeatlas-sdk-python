# codeatlas-sdk (Python)

Typed Python client for the public [CodeAtlas](https://codeatlas.com.br) API. Read-only, no authentication, no dependencies.
API docs: https://codeatlas.com.br/docs · OpenAPI: https://codeatlas.com.br/openapi.json

```sh
pip install codeatlas-sdk
```

```python
# import name is `codeatlas`
from codeatlas import CodeAtlas, CodeAtlasError

client = CodeAtlas()  # base_url defaults to https://codeatlas.com.br/api/v1

page = client.services.list(limit=20)
print(page.count, page.data[0].name, page.next_cursor)

for service in client.services.iterate():
    print(service.slug)

service = client.services.get("zelvo-ai")
hits = client.services.search("whatsapp")  # client-side filter, the API has no search endpoint

try:
    client.services.get("nope")
except CodeAtlasError as error:
    print(error.status, error.code, error.hint)
```

## Contact requests (needs OAuth credentials)

```python
from codeatlas import CodeAtlas, SANDBOX_BASE_URL

credentials = CodeAtlas.register("my-agent")  # store the secret, it is shown once
client = CodeAtlas(credentials=credentials)   # base_url=SANDBOX_BASE_URL validates without storing or sending

request = client.contact_requests.create(
    "Ana Souza", "ana@example.com", "Quero um diagnóstico do meu atendimento.",
    service_slug="zelvo-ai", idempotency_key="8f3c2a10-5d4e-4b7a-9c1e-2f6a7b8c9d0e",
)
print(request.id, request.status)  # cr_..., "received"
```

```python
results = client.services.batch(["zelvo-ai", "consultoria"])  # up to 50 slugs; unknown ones are 404 items

job = client.exports.create("csv")          # "jsonl", "csv" or "md"; 10 per hour per client
job = client.exports.wait(job.id)
file = client.exports.download(job.id)
```

The client fetches and caches the OAuth token (client credentials) for you.

## Development

```sh
uv run --with pytest --with . pytest   # hits the live API
uv build
```

Releases: push a tag `vX.Y.Z`; the workflow publishes to PyPI via trusted publishing.

MIT licensed. Same surface as [@codeatlas/sdk](https://github.com/codeatlasdev/codeatlas-sdk-js).
