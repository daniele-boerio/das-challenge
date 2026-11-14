"""La reference dev'essere una scultura in pasta da modellare, non il soggetto vero."""

import io
import json

import httpx
import pytest
from PIL import Image

from app import config, references


def _jpeg(color):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, "JPEG")
    return buf.getvalue()


OPENVERSE_RESULTS = [
    {"url": "https://img/real-owl.jpg", "thumbnail": "https://img/real-owl-t.jpg", "title": "Owl in the forest",
     "tags": [{"name": "bird"}], "license": "by", "license_version": "2.0"},
    {"url": "https://img/clay-owl.jpg", "thumbnail": "https://img/clay-owl-t.jpg", "title": "Little owl",
     "tags": [{"name": "polymer clay"}, {"name": "handmade"}], "license": "by", "license_version": "2.0",
     "creator": "Ada", "foreign_landing_url": "https://flickr/1"},
    {"url": "https://img/fimo-owl.jpg", "thumbnail": "https://img/fimo-owl-t.jpg", "title": "Fimo owl figurine",
     "tags": [], "license": "cc0", "license_version": "1.0"},
]


@pytest.fixture
def net(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        if request.url.host == "api.openverse.org":
            return httpx.Response(200, json={"results": OPENVERSE_RESULTS})
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(200, json={"query": {"pages": {}}})
        return httpx.Response(200, content=_jpeg((200, 120, 40)))

    monkeypatch.setattr(references, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def test_queries_ask_for_clay():
    assert all("clay" in q or "plasticine" in q for q in references.queries("owl"))
    assert references.is_clay("Cute FIMO frog") and references.is_clay("air-dry clay cat")
    assert not references.is_clay("Edible fungi in basket") and not references.is_clay("Das Haus")


def test_only_clay_results_without_ai(net, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with references._client() as c:
        found = references.candidates(c, "owl")
    assert {f["image"] for f in found} == {"https://img/clay-owl.jpg", "https://img/fimo-owl.jpg"}
    name, attr = references.fetch("owl", subject="Gufo")
    assert name and attr["provider"] == "Openverse" and "real" not in str(net[-1])


def test_ai_picks_the_sculpture(net, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    sent = {}

    def fake_post(url, **kw):
        sent.update(kw["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"best": 2, "reason": "ok"})}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    import random

    name, attr = references.fetch("owl", rng=random.Random(1), subject="Gufo")
    images = [p for p in sent["messages"][1]["content"] if p["type"] == "image_url"]
    assert len(images) == 2 and "Gufo" in sent["messages"][1]["content"][-1]["text"]
    assert name
    # la seconda miniatura mostrata è quella scaricata per intero
    thumbs = [u for u in net if u.endswith("-t.jpg")]
    assert net[-1] == thumbs[1].replace("-t.jpg", ".jpg")


def test_ai_finds_nothing(net, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(
        httpx, "post",
        lambda url, **kw: httpx.Response(200, json={"choices": [{"message": {"content": '{"best": null, "reason": "no"}'}}]}),
    )
    assert references.fetch("owl", subject="Gufo") == (None, None)


def test_ai_failure_falls_back_to_clay_results(net, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")

    def boom(url, **kw):
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(httpx, "post", boom)
    name, attr = references.fetch("owl", subject="Gufo")
    assert name and net[-1] in ("https://img/clay-owl.jpg", "https://img/fimo-owl.jpg")
