import pytest

from codeatlas import CodeAtlas, CodeAtlasError

client = CodeAtlas()


def test_health():
    health = client.health()
    assert health.status == "ok"
    assert health.service == "codeatlas-api"


def test_list_paginates():
    first = client.services.list(limit=1)
    assert len(first.data) == 1
    assert first.next_cursor is not None
    second = client.services.list(limit=1, cursor=first.next_cursor)
    assert second.data[0].slug != first.data[0].slug


def test_iterate_yields_whole_catalog():
    one_by_one = [s.slug for s in client.services.iterate(limit=1)]
    assert one_by_one == [s.slug for s in client.services.list(limit=100).data]


def test_get():
    slug = client.services.list(limit=1).data[0].slug
    service = client.services.get(slug)
    assert service.slug == slug
    assert service.capabilities


def test_get_unknown_raises():
    with pytest.raises(CodeAtlasError) as info:
        client.services.get("does-not-exist")
    assert info.value.status == 404
    assert info.value.code == "not_found"
    assert info.value.hint


def test_search():
    assert client.services.search("whatsapp")
    assert client.services.search("zzz-no-match-zzz") == []
