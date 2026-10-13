# codeatlas (Python)

Typed Python client for the public [CodeAtlas](https://codeatlas.com.br) API. Read-only, no authentication, no dependencies.
API docs: https://codeatlas.com.br/docs · OpenAPI: https://codeatlas.com.br/openapi.json

```sh
pip install codeatlas
```

```python
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

## Development

```sh
uv run --with pytest --with . pytest   # hits the live API
uv build
```

Releases: push a tag `vX.Y.Z`; the workflow publishes to PyPI via trusted publishing.

MIT licensed. Same surface as [@codeatlas/sdk](https://github.com/codeatlasdev/codeatlas-sdk-js).
