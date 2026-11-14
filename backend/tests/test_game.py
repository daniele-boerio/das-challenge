import pytest
from starlette.websockets import WebSocketDisconnect

from app import config, game, judge
from tests.conftest import login, new_player


def setup_match(client, settings=None):
    """Daniele (sul client principale) crea, Giulia (su un altro dispositivo) entra."""
    host = login(client, "dani@example.com", "Daniele")
    r = host.post("/api/matches", json={"settings": settings or {"judge": "voto"}})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    guest = new_player(client, "giulia@example.com", "Giulia")
    r = guest.post(f"/api/matches/{code}/join")
    assert r.status_code == 200, r.text
    return code, host, guest


def upload(player, code, n, jpeg):
    return player.post(
        f"/api/matches/{code}/rounds/{n}/photo",
        files={"photo": ("p.jpg", jpeg(), "image/jpeg")},
    )


def play_round(code, host, guest, jpeg, n=1, votes=(5, 6), difficulty="facile"):
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": difficulty})
    upload(host, code, n, jpeg)
    upload(guest, code, n, jpeg)
    host.post(f"/api/matches/{code}/rounds/{n}/vote", json={"value": votes[0]})
    return guest.post(f"/api/matches/{code}/rounds/{n}/vote", json={"value": votes[1]}).json()


# ── accesso ───────────────────────────────────────────────────────────────────


def test_login_with_code_and_name(app_env):
    client, _ = app_env
    assert client.get("/api/auth/me").json() == {"user": None}
    assert client.post("/api/auth/request", json={"email": "Dani@Example.com"}).status_code == 200
    code = client.sent_codes["dani@example.com"]
    bad = "000000" if code != "000000" else "111111"
    r = client.post("/api/auth/verify", json={"email": "dani@example.com", "code": bad})
    assert r.status_code == 400 and "tentativi" in r.json()["detail"]
    r = client.post("/api/auth/verify", json={"email": "dani@example.com", "code": code})
    assert r.status_code == 200
    assert r.json()["user"]["name"] is None
    # senza nome non si gioca
    assert client.post("/api/matches", json={}).status_code == 409
    client.post("/api/auth/name", json={"name": "Daniele"})
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == "dani@example.com" and me["name"] == "Daniele"
    # il codice si usa una volta sola
    assert client.post("/api/auth/verify", json={"email": "dani@example.com", "code": code}).status_code == 400


def test_code_resend_cooldown_and_allowlist(app_env):
    client, mp = app_env
    client.post("/api/auth/request", json={"email": "a@example.com"})
    assert client.post("/api/auth/request", json={"email": "a@example.com"}).status_code == 429
    mp.setattr(config, "ALLOWED_EMAILS", {"ok@example.com"})
    assert client.post("/api/auth/request", json={"email": "no@example.com"}).status_code == 403
    assert client.post("/api/auth/request", json={"email": "ok@example.com"}).status_code == 200


def test_logged_out_cannot_play(app_env):
    client, _ = app_env
    assert client.post("/api/matches", json={}).status_code == 401
    assert client.get("/api/gallery").status_code == 401


# ── partita ───────────────────────────────────────────────────────────────────


def test_create_join_and_full(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    st = guest.get(f"/api/matches/{code}").json()
    assert st["you"] == "guest" and st["status"] == "ready"
    assert st["players"]["guest"]["name"] == "Giulia"
    third = new_player(client, "terzo@example.com", "Terzo")
    assert third.post(f"/api/matches/{code}/join").status_code == 409


def test_cannot_join_own_match(app_env):
    client, _ = app_env
    host = login(client, "dani@example.com", "Daniele")
    code = host.post("/api/matches", json={}).json()["code"]
    assert host.post(f"/api/matches/{code}/join").status_code == 400


def test_only_host_starts_round(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    assert guest.post(f"/api/matches/{code}/rounds", json={}).status_code == 403
    r = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"})
    assert r.status_code == 200, r.text
    rnd = r.json()["rounds"][0]
    assert rnd["difficulty"] == "difficile" and rnd["multiplier"] == 2.0
    assert rnd["image"].startswith("/api/media/")
    assert rnd["duration_s"] == 40 * 60
    assert host.post(f"/api/matches/{code}/rounds", json={}).status_code == 409


def test_vote_flow_hides_until_both(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "rounds": 2})
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "media"})
    rnd = upload(host, code, 1, jpeg).json()["rounds"][0]
    assert rnd["status"] == "sculpting" and rnd["delivered"]["host"]
    assert guest.get(f"/api/matches/{code}").json()["rounds"][0]["photos"]["host"] is None
    st = upload(guest, code, 1, jpeg).json()
    assert st["rounds"][0]["status"] == "judging" and st["rounds"][0]["photos"]["host"]

    st = host.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 8}).json()
    assert st["rounds"][0]["votes"]["mine"] == 8
    assert "host" not in guest.get(f"/api/matches/{code}").json()["rounds"][0]["votes"]
    st = guest.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 6.5}).json()
    rnd = st["rounds"][0]
    assert rnd["status"] == "done"
    assert rnd["scores"] == {"host": 6.5, "guest": 8.0}
    assert rnd["points"] == {"host": 9.8, "guest": 12.0}
    assert st["status"] == "ready" and st["players"]["guest"]["total"] == 12.0


def test_match_ends_after_last_round_and_rematch(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "rounds": 1})
    st = play_round(code, host, guest, jpeg, votes=(3, 9))
    assert st["status"] == "finished" and st["winner"] == "host"

    g = guest.get("/api/gallery").json()
    assert g["matches"][0]["code"] == code
    h2h = g["head_to_head"][0]
    assert h2h["wins"]["Daniele"] == 1 and h2h["matches"] == 1

    r = guest.post(f"/api/matches/{code}/rematch")
    assert r.status_code == 200
    new = r.json()["code"]
    assert host.get(f"/api/matches/{code}").json()["rematch_code"] == new
    assert r.json()["state"]["players"]["host"]["name"] == "Giulia"
    assert host.post(f"/api/matches/{new}/join").status_code == 200


def test_powerups(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    base = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}).json()["rounds"][0]["end_at"]
    st = host.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}).json()
    assert st["rounds"][0]["end_at"]["host"] == base["host"] + 120
    st = host.post(f"/api/matches/{code}/powerups", json={"kind": "sabotage"}).json()
    assert st["rounds"][0]["end_at"]["guest"] == base["guest"] - 60
    assert st["players"]["host"]["powerups"] == {"extra": False, "sabotage": False, "reroll": True}
    assert host.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}).status_code == 400
    old_subject = st["rounds"][0]["subject"]
    rnd = guest.post(f"/api/matches/{code}/powerups", json={"kind": "reroll"}).json()["rounds"][0]
    assert rnd["subject"] != old_subject
    assert rnd["end_at"]["host"] == rnd["end_at"]["guest"]


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
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"})
    upload(host, code, 1, jpeg)
    upload(guest, code, 1, jpeg)
    rnd = host.get(f"/api/matches/{code}").json()["rounds"][0]
    assert len(calls) == 1 and calls[0]["reference"]
    assert calls[0]["host_name"] == "Daniele" and calls[0]["guest_name"] == "Giulia"
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
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    upload(host, code, 1, jpeg)
    upload(guest, code, 1, jpeg)
    rnd = host.get(f"/api/matches/{code}").json()["rounds"][0]
    assert rnd["status"] == "judging" and rnd["ai"]["status"] == "failed"
    assert rnd["votes"]["needed"]
    host.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 5})
    st = guest.post(f"/api/matches/{code}/rounds/1/vote", json={"value": 5}).json()
    assert st["rounds"][0]["status"] == "done"


def test_handicap_goes_to_leader(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "handicap": "leader", "memory": False, "rounds": 3})
    play_round(code, host, guest, jpeg, votes=(2, 9))
    st = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}).json()
    hc = st["rounds"][1]["handicaps"]
    assert hc["host"] and not hc["guest"]


def test_only_players_see_match_and_gallery(app_env, jpeg):
    client, _ = app_env
    code, host, guest = setup_match(client, {"judge": "voto", "rounds": 1})
    outsider = new_player(client, "altro@example.com", "Altro")
    other_guest = new_player(client, "amico@example.com", "Amico")
    other_code = outsider.post("/api/matches", json={"settings": {"judge": "voto", "rounds": 1}}).json()["code"]
    # prima che l'avversario entri la partita si vede (serve per entrare dal link)
    assert host.get(f"/api/matches/{other_code}").status_code == 200
    other_guest.post(f"/api/matches/{other_code}/join")
    assert host.get(f"/api/matches/{other_code}").status_code == 403
    assert outsider.get(f"/api/matches/{code}").status_code == 403

    play_round(code, host, guest, jpeg)
    play_round(other_code, outsider, other_guest, jpeg)
    assert [m["code"] for m in host.get("/api/gallery").json()["matches"]] == [code]
    assert [m["code"] for m in outsider.get("/api/gallery").json()["matches"]] == [other_code]


def test_websocket(app_env):
    client, _ = app_env
    # il client principale (quello con il loop dei WebSocket) è l'ospite
    host = new_player(client, "dani@example.com", "Daniele")
    code = host.post("/api/matches", json={}).json()["code"]
    login(client, "giulia@example.com", "Giulia")
    client.post(f"/api/matches/{code}/join")
    with client.websocket_connect(f"/api/ws/{code}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state" and msg["state"]["you"] == "guest"
        assert msg["state"]["players"]["guest"]["online"]
        host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
        msg = ws.receive_json()
        assert msg["state"]["status"] == "playing"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_websocket_refuses_outsiders(app_env):
    client, _ = app_env
    code, host, guest = setup_match(client)
    client.post("/api/auth/logout")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/ws/{code}") as ws:
            ws.receive_json()
    assert exc.value.code == 4403


def test_settings_are_clamped():
    s = game.clean_settings({"rounds": 99, "judge": "ai", "minutes": {"facile": 0}, "theme": "boh"})
    assert s["rounds"] == 10 and s["minutes"]["facile"] == 1 and s["theme"] == "misto"
    assert s["judge"] == "voto"  # niente chiave → niente AI


def test_judge_parse_fallback():
    assert judge._parse('```json\n{"A": 1}\n```') == {"A": 1}


def test_judge_request_and_mapping(app_env, jpeg):
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
    host_is_a = random.Random(0).random() < 0.5
    out = judge.judge("Mela", "facile", names[0], names[1], names[2], "Dani", "Giu", rng=random.Random(0))
    assert sent["url"].endswith("/chat/completions") and sent["auth"] == "Bearer sk-or-test"
    parts = sent["messages"][1]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 3
    a, b = {"score": 3.0, "comment": "a"}, {"score": 10.0, "comment": "b"}
    assert out["host"] == (a if host_is_a else b)
    assert out["guest"] == (b if host_is_a else a)
