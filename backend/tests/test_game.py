from app import config, game, judge
from tests.conftest import H


def setup_match(client, settings=None):
    r = client.post("/api/matches", json={"name": "Daniele", "settings": settings or {"judge": "voto"}})
    assert r.status_code == 200, r.text
    code, host = r.json()["code"], r.json()["token"]
    r = client.post(f"/api/matches/{code}/join", json={"name": "Giulia"})
    assert r.status_code == 200, r.text
    return code, host, r.json()["token"]


def upload(client, code, n, token, jpeg):
    return client.post(
        f"/api/matches/{code}/rounds/{n}/photo",
        files={"photo": ("p.jpg", jpeg(), "image/jpeg")},
        headers=H(token),
    )


def test_create_join_and_full(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    st = client.get(f"/api/matches/{code}", headers=H(guest)).json()
    assert st["you"] == "guest" and st["status"] == "ready"
    assert st["players"]["guest"]["name"] == "Giulia"
    assert client.post(f"/api/matches/{code}/join", json={"name": "Terzo"}).status_code == 409


def test_only_host_starts_round(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    assert client.post(f"/api/matches/{code}/rounds", json={}, headers=H(guest)).status_code == 403
    r = client.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"}, headers=H(host))
    assert r.status_code == 200, r.text
    rnd = r.json()["rounds"][0]
    assert rnd["difficulty"] == "difficile" and rnd["multiplier"] == 2.0
    assert rnd["image"].startswith("/api/media/")
    assert rnd["duration_s"] == 40 * 60
    # un secondo round non parte finché il primo è aperto
    assert client.post(f"/api/matches/{code}/rounds", json={}, headers=H(host)).status_code == 409


def test_vote_flow_hides_until_both(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "rounds": 2})
    client.post(f"/api/matches/{code}/rounds", json={"difficulty": "media"}, headers=H(host))
    st = upload(client, code, 1, host, jpeg).json()
    rnd = st["rounds"][0]
    assert rnd["status"] == "sculpting" and rnd["delivered"]["host"]
    # l'avversaria non vede la mia foto prima di aver consegnato
    st_g = client.get(f"/api/matches/{code}", headers=H(guest)).json()
    assert st_g["rounds"][0]["photos"]["host"] is None
    st = upload(client, code, 1, guest, jpeg).json()
    assert st["rounds"][0]["status"] == "judging"
    assert st["rounds"][0]["photos"]["host"]

    st = client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 8}, headers=H(host)).json()
    assert st["rounds"][0]["votes"]["mine"] == 8
    st_g = client.get(f"/api/matches/{code}", headers=H(guest)).json()
    assert "host" not in st_g["rounds"][0]["votes"]  # voto ancora nascosto
    st = client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 6.5}, headers=H(guest)).json()
    rnd = st["rounds"][0]
    assert rnd["status"] == "done"
    # host ha ricevuto 6.5 da guest, ×1.5 in media
    assert rnd["scores"] == {"host": 6.5, "guest": 8.0}
    assert rnd["points"] == {"host": 9.8, "guest": 12.0}
    assert st["status"] == "ready"
    assert st["players"]["guest"]["total"] == 12.0


def test_match_ends_after_last_round_and_rematch(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "rounds": 1})
    client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host))
    upload(client, code, 1, host, jpeg)
    upload(client, code, 1, guest, jpeg)
    client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 3}, headers=H(host))
    st = client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 9}, headers=H(guest)).json()
    assert st["status"] == "finished" and st["winner"] == "host"

    g = client.get("/api/gallery").json()
    assert g["matches"][0]["code"] == code
    h2h = g["head_to_head"][0]
    assert h2h["wins"]["Daniele"] == 1 and h2h["matches"] == 1

    r = client.post(f"/api/matches/{code}/rematch", headers=H(guest))
    assert r.status_code == 200
    new = r.json()["code"]
    assert client.get(f"/api/matches/{code}").json()["rematch_code"] == new
    assert r.json()["state"]["players"]["host"]["name"] == "Giulia"


def test_powerups(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    st = client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host)).json()
    base = st["rounds"][0]["end_at"]
    st = client.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}, headers=H(host)).json()
    assert st["rounds"][0]["end_at"]["host"] == base["host"] + 120
    st = client.post(f"/api/matches/{code}/powerups", json={"kind": "sabotage"}, headers=H(host)).json()
    assert st["rounds"][0]["end_at"]["guest"] == base["guest"] - 60
    assert st["players"]["host"]["powerups"] == {"extra": False, "sabotage": False, "reroll": True}
    # una volta sola per partita
    assert client.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}, headers=H(host)).status_code == 400
    old_subject = st["rounds"][0]["subject"]
    st = client.post(f"/api/matches/{code}/powerups", json={"kind": "reroll"}, headers=H(guest)).json()
    rnd = st["rounds"][0]
    assert rnd["subject"] != old_subject
    assert rnd["end_at"]["host"] == rnd["end_at"]["guest"]  # il round riparte uguale per tutti


def test_ai_judge(app_env, jpeg):
    client, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    calls = []

    def fake(**kw):
        calls.append(kw)
        return {
            "host": {"score": 7.0, "comment": "Bella forma"},
            "guest": {"score": 9.0, "comment": "Identico"},
            "verdict": "Vince Giulia",
        }

    mp.setattr(judge, "judge", fake)
    code, host, guest = setup_match(client, {"judge": "ai"})
    client.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"}, headers=H(host))
    upload(client, code, 1, host, jpeg)
    upload(client, code, 1, guest, jpeg)
    rnd = client.get(f"/api/matches/{code}", headers=H(host)).json()["rounds"][0]
    assert len(calls) == 1 and calls[0]["reference"]
    assert rnd["status"] == "done"
    assert rnd["points"] == {"host": 14.0, "guest": 18.0}
    assert rnd["ai"]["result"]["verdict"] == "Vince Giulia"


def test_ai_failure_falls_back_to_votes(app_env, jpeg):
    client, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")

    def boom(**kw):
        raise RuntimeError("rete giù")

    mp.setattr(judge, "judge", boom)
    code, host, guest = setup_match(client, {"judge": "ai"})
    client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host))
    upload(client, code, 1, host, jpeg)
    upload(client, code, 1, guest, jpeg)
    rnd = client.get(f"/api/matches/{code}", headers=H(host)).json()["rounds"][0]
    assert rnd["status"] == "judging" and rnd["ai"]["status"] == "failed"
    assert rnd["votes"]["needed"]
    client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 5}, headers=H(host))
    st = client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 5}, headers=H(guest)).json()
    assert st["rounds"][0]["status"] == "done"


def test_handicap_goes_to_leader(app_env, jpeg):
    client, mp = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "handicap": "leader", "memory": False})
    client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host))
    upload(client, code, 1, host, jpeg)
    upload(client, code, 1, guest, jpeg)
    client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 2}, headers=H(host))
    client.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 9}, headers=H(guest))
    st = client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host)).json()
    hc = st["rounds"][1]["handicaps"]
    assert hc["host"] and not hc["guest"]


def test_access_code(app_env):
    client, mp = app_env
    mp.setattr(config, "ACCESS_CODE", "segreto")
    assert client.post("/api/matches", json={"name": "X"}).status_code == 401
    r = client.post("/api/matches", json={"name": "X"}, headers={"X-Access-Code": "segreto"})
    assert r.status_code == 200
    # chi entra col link non ha bisogno del codice
    assert client.post(f"/api/matches/{r.json()['code']}/join", json={"name": "Y"}).status_code == 200
    assert client.get("/api/gallery").status_code == 401


def test_websocket_receives_state(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    with client.websocket_connect(f"/api/ws/{code}?token={guest}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state" and msg["state"]["you"] == "guest"
        assert msg["state"]["players"]["guest"]["online"]
        client.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}, headers=H(host))
        msg = ws.receive_json()
        assert msg["state"]["status"] == "playing"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_settings_are_clamped():
    s = game.clean_settings({"rounds": 99, "judge": "ai", "minutes": {"facile": 0}, "theme": "boh"})
    assert s["rounds"] == 10 and s["minutes"]["facile"] == 1 and s["theme"] == "misto"
    assert s["judge"] == "voto"  # niente chiave → niente AI


def test_judge_parse_fallback():
    assert judge._parse('```json\n{"A": 1}\n```') == {"A": 1}


def test_judge_request_and_mapping(app_env, jpeg, tmp_path):
    """Il giudice manda tre immagini a OpenRouter e rimappa A/B su host/guest."""
    import json as _json
    import random

    import httpx

    from app import media

    _, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    names = [media.save_image(jpeg(), "x") for _ in range(3)]
    sent = {}

    def fake_post(url, **kw):
        sent.update(kw["json"], url=url, auth=kw["headers"]["Authorization"])
        body = {"A": {"score": 3, "comment": "a"}, "B": {"score": 11, "comment": "b"}, "verdict": "v"}
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(body)}}]})

    mp.setattr(httpx, "post", fake_post)
    rng = random.Random(0)
    host_is_a = random.Random(0).random() < 0.5
    out = judge.judge("Mela", "facile", names[0], names[1], names[2], "Dani", "Giu", rng=rng)
    assert sent["url"].endswith("/chat/completions") and sent["auth"] == "Bearer sk-or-test"
    parts = sent["messages"][1]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 3
    a, b = {"score": 3.0, "comment": "a"}, {"score": 10.0, "comment": "b"}  # 11 → 10
    assert out["host"] == (a if host_is_a else b)
    assert out["guest"] == (b if host_is_a else a)
