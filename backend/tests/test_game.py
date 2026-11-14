import pytest
from starlette.websockets import WebSocketDisconnect

from app import config, game, judge
from tests.conftest import login, new_player


NAMES = ["Giulia", "Marco", "Sara", "Luca", "Anna", "Paolo", "Elena", "Ugo"]


def setup_match(client, settings=None, players=2):
    """Daniele (sul client principale) crea, gli altri (ciascuno sul suo
    dispositivo) entrano. Restituisce (codice, [client per posto])."""
    host = login(client, "dani@example.com", "Daniele")
    r = host.post("/api/matches", json={"settings": settings or {"judge": "voto"}})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    seats = [host]
    for name in NAMES[: players - 1]:
        p = new_player(client, f"{name.lower()}@example.com", name)
        r = p.post(f"/api/matches/{code}/join")
        assert r.status_code == 200, r.text
        seats.append(p)
    return code, seats


def upload(player, code, n, jpeg):
    return player.post(
        f"/api/matches/{code}/rounds/{n}/photo",
        files={"photo": ("p.jpg", jpeg(), "image/jpeg")},
    )


def entries(state, n=1):
    return {e["seat"]: e for e in state["rounds"][n - 1]["entries"]}


def vote_all(code, seats, n, value_for):
    """Ognuno vota tutti gli altri: value_for(chi vota, chi è votato)."""
    out = None
    for i, p in enumerate(seats):
        votes = {str(j): value_for(i, j) for j in range(len(seats)) if j != i}
        r = p.post(f"/api/matches/{code}/rounds/{n}/vote", json={"votes": votes})
        assert r.status_code == 200, r.text
        out = r.json()
    return out


def play_round(code, seats, jpeg, n=1, value_for=lambda i, j: 5, difficulty="facile"):
    seats[0].post(f"/api/matches/{code}/rounds", json={"difficulty": difficulty})
    for p in seats:
        upload(p, code, n, jpeg)
    return vote_all(code, seats, n, value_for)


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


def test_create_join_up_to_eight(app_env):
    client, _ = app_env
    code, seats = setup_match(client, players=8)
    st = seats[3].get(f"/api/matches/{code}").json()
    assert st["you"] == 3 and st["status"] == "lobby"
    assert [p["name"] for p in st["players"]] == ["Daniele", *NAMES[:7]]
    ninth = new_player(client, "nono@example.com", "Nono")
    r = ninth.post(f"/api/matches/{code}/join")
    assert r.status_code == 409 and "completo" in r.json()["detail"]
    # piena: chi non gioca non la vede più
    assert ninth.get(f"/api/matches/{code}").status_code == 403


def test_join_closes_when_first_round_starts(app_env):
    client, _ = app_env
    code, (host, guest) = setup_match(client)
    late = new_player(client, "tardi@example.com", "Tardi")
    assert late.get(f"/api/matches/{code}").status_code == 200  # in sala d'attesa si vede
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    assert late.post(f"/api/matches/{code}/join").status_code == 409
    assert late.get(f"/api/matches/{code}").status_code == 403


def test_same_name_gets_a_number(app_env):
    client, _ = app_env
    host = login(client, "dani@example.com", "Daniele")
    code = host.post("/api/matches", json={}).json()["code"]
    for i in range(2):
        p = new_player(client, f"omonimo{i}@example.com", "Daniele")
        p.post(f"/api/matches/{code}/join")
    names = [p["name"] for p in host.get(f"/api/matches/{code}").json()["players"]]
    assert names == ["Daniele", "Daniele (2)", "Daniele (3)"]


def test_cannot_join_own_match_or_start_alone(app_env):
    client, _ = app_env
    host = login(client, "dani@example.com", "Daniele")
    code = host.post("/api/matches", json={}).json()["code"]
    assert host.post(f"/api/matches/{code}/join").status_code == 400
    r = host.post(f"/api/matches/{code}/rounds", json={})
    assert r.status_code == 400 and "avversario" in r.json()["detail"]


def test_only_host_starts_round(app_env):
    client, _ = app_env
    code, (host, guest) = setup_match(client)
    assert guest.post(f"/api/matches/{code}/rounds", json={}).status_code == 403
    r = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"})
    assert r.status_code == 200, r.text
    rnd = r.json()["rounds"][0]
    assert rnd["difficulty"] == "difficile" and rnd["multiplier"] == 2.0
    assert rnd["image"].startswith("/api/media/")
    assert rnd["duration_s"] == 40 * 60 and rnd["timed"]
    assert len(rnd["entries"]) == 2
    assert host.post(f"/api/matches/{code}/rounds", json={}).status_code == 409


def test_vote_flow_with_three_players(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "rounds": 2}, players=3)
    host, a, b = seats
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "media"})
    st = upload(host, code, 1, jpeg).json()
    assert st["rounds"][0]["status"] == "sculpting" and entries(st)[0]["delivered"]
    # le foto degli altri restano nascoste finché non hanno consegnato tutti
    assert entries(a.get(f"/api/matches/{code}").json())[0]["photo"] is None
    upload(a, code, 1, jpeg)
    st = upload(b, code, 1, jpeg).json()
    rnd = st["rounds"][0]
    assert rnd["status"] == "judging" and all(e["photo"] for e in rnd["entries"])
    assert rnd["votes"]["targets"] == [0, 1]

    # bisogna votare tutti gli altri
    r = host.post(f"/api/matches/{code}/rounds/1/vote", json={"votes": {"1": 8}})
    assert r.status_code == 400 and "Marco" in r.json()["detail"]
    # Daniele: Giulia 8, Marco 4 · Giulia: Daniele 6, Marco 6 · Marco: Daniele 7, Giulia 9
    grid = {(0, 1): 8, (0, 2): 4, (1, 0): 6, (1, 2): 6, (2, 0): 7, (2, 1): 9}
    st = vote_all(code, seats, 1, lambda i, j: grid[(i, j)])
    rnd = st["rounds"][0]
    assert rnd["status"] == "done"
    e = entries(st)
    assert (e[0]["score"], e[1]["score"], e[2]["score"]) == (6.5, 8.5, 5.0)
    assert (e[0]["points"], e[1]["points"], e[2]["points"]) == (9.8, 12.8, 7.5)
    assert sorted(e[1]["votes_received"]) == [8, 9]
    assert st["status"] == "ready"
    assert [p["total"] for p in st["players"]] == [9.8, 12.8, 7.5]


def test_host_can_close_votes(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "rounds": 1}, players=3)
    host, a, b = seats
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    for p in seats:
        upload(p, code, 1, jpeg)
    host.post(f"/api/matches/{code}/rounds/1/vote", json={"votes": {"1": 6, "2": 8}})
    assert a.post(f"/api/matches/{code}/rounds/1/close-votes").status_code == 403
    st = host.post(f"/api/matches/{code}/rounds/1/close-votes").json()
    e = entries(st)
    assert st["status"] == "finished"
    assert (e[0]["score"], e[1]["score"], e[2]["score"]) == (0.0, 6.0, 8.0)
    assert st["winners"] == [2]


def test_match_ends_after_last_round_and_rematch(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "rounds": 1}, players=3)
    host, a, b = seats
    # Giulia prende 9 da tutti, gli altri 3
    st = play_round(code, seats, jpeg, value_for=lambda i, j: 9 if j == 1 else 3)
    assert st["status"] == "finished" and st["winners"] == [1]

    g = b.get("/api/gallery").json()
    assert g["matches"][0]["code"] == code and g["stats"] == {"played": 1, "won": 0}
    h2h = {h["name"]: h for h in g["head_to_head"]}
    assert h2h["Giulia"]["losses"] == 1 and h2h["Daniele"]["draws"] == 1
    assert len(g["matches"][0]["rounds"][0]["photos"]) == 3

    r = a.post(f"/api/matches/{code}/rematch")
    assert r.status_code == 200
    new = r.json()["code"]
    assert host.get(f"/api/matches/{code}").json()["rematch_code"] == new
    assert r.json()["state"]["players"][0]["name"] == "Giulia"
    assert host.post(f"/api/matches/{new}/join").status_code == 200
    assert b.post(f"/api/matches/{new}/join").status_code == 200


def test_finish_early_ranks_everyone(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "rounds": 5}, players=2)
    host, guest = seats
    assert host.post(f"/api/matches/{code}/finish").status_code == 400  # nessun round ancora
    play_round(code, seats, jpeg)
    assert guest.post(f"/api/matches/{code}/finish").status_code == 403
    st = host.post(f"/api/matches/{code}/finish").json()
    assert st["status"] == "finished" and st["winners"] == [0, 1]


def test_references_are_prepared_ahead(app_env, jpeg, monkeypatch):
    """Il round prende la reference già pronta invece di cercarla al momento."""
    from app import main, references

    client, mp = app_env
    calls = []
    real = references.fetch
    mp.setattr(references, "fetch", lambda q, rng=None, subject=None: calls.append(q) or real(q))
    mp.setattr(main, "PREFETCH", True)
    started = []
    mp.setattr(main.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: started.append((target, args))})())
    code, (host, guest) = setup_match(client, {"judge": "voto", "rounds": 2})
    target, args = started.pop(0)
    target(*args)  # il thread, qui in primo piano
    assert len(calls) == 3 and len(main._ready) == 3
    n = len(calls)
    st = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"}).json()
    assert len(calls) == n  # nessuna ricerca al momento
    assert st["rounds"][0]["difficulty"] == "difficile" and st["rounds"][0]["image"]
    target, args = started.pop(0)
    target(*args)  # rifà la scorta della difficile, con un soggetto diverso
    subjects = {main._ready[(code, d)][0][0] for d in ("facile", "media", "difficile")}
    assert st["rounds"][0]["subject"] not in subjects and len(calls) == n + 1
    # a partita finita il ticker butta la scorta, file compresi
    from app import db, media
    from app.models import Match

    files = [it[1] for it in main._ready.values()]
    with db.session_scope() as s:
        s.query(Match).filter(Match.code == code).update({"status": "finished"})
    main.tick_all()
    assert not main._ready and not any(media.path_of(f).exists() for f in files)


# ── tempo ─────────────────────────────────────────────────────────────────────


def test_powerups_and_sabotage_target(app_env):
    client, _ = app_env
    code, seats = setup_match(client, players=3)
    host, a, b = seats
    st = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}).json()
    base = {e["seat"]: e["end_at"] for e in st["rounds"][0]["entries"]}
    st = host.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}).json()
    assert entries(st)[0]["end_at"] == base[0] + 120
    r = host.post(f"/api/matches/{code}/powerups", json={"kind": "sabotage"})
    assert r.status_code == 400 and "chi" in r.json()["detail"]
    st = host.post(f"/api/matches/{code}/powerups", json={"kind": "sabotage", "target": 2}).json()
    e = entries(st)
    assert e[2]["end_at"] == base[2] - 60 and e[1]["end_at"] == base[1]
    assert st["rounds"][0]["events"][-1]["target"] == 2
    assert st["players"][0]["powerups"] == {"extra": False, "sabotage": False, "reroll": True}
    assert host.post(f"/api/matches/{code}/powerups", json={"kind": "extra"}).status_code == 400
    old_subject = st["rounds"][0]["subject"]
    rnd = a.post(f"/api/matches/{code}/powerups", json={"kind": "reroll"}).json()["rounds"][0]
    assert rnd["subject"] != old_subject
    assert len({e["end_at"] for e in rnd["entries"]}) == 1


def test_strict_timer_closes_deliveries(app_env, jpeg, clock):
    from app import main

    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "timer": "rigido", "rounds": 2}, players=3)
    host, a, b = seats
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})  # 15 minuti
    upload(host, code, 1, jpeg)
    clock.advance(15 * 60 + 30)  # tempo scaduto, ma c'è ancora il minuto per la foto
    assert upload(a, code, 1, jpeg).status_code == 200
    clock.advance(60)
    r = upload(b, code, 1, jpeg)
    assert r.status_code == 400 and "scaduto" in r.json()["detail"]
    main.tick_all()
    st = host.get(f"/api/matches/{code}").json()
    assert st["rounds"][0]["status"] == "judging"
    # Marco non ha consegnato: vota lo stesso, ma nessuno vota lui
    assert st["rounds"][0]["votes"]["targets"] == [1]
    assert b.get(f"/api/matches/{code}").json()["rounds"][0]["votes"]["targets"] == [0, 1]
    st = vote_all(code, seats, 1, lambda i, j: 7)
    e = entries(st)
    assert st["rounds"][0]["status"] == "done"
    assert e[2]["points"] == 0 and e[0]["score"] == 7


def test_free_timer_lets_you_finish_late(app_env, jpeg, clock):
    client, _ = app_env
    code, (host, guest) = setup_match(client, {"judge": "voto"})
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    clock.advance(3 * 3600)
    assert upload(guest, code, 1, jpeg).status_code == 200


def test_no_timer(app_env, jpeg, clock):
    from app import main

    client, _ = app_env
    code, (host, guest) = setup_match(client, {"judge": "voto", "timer": "nessuno"})
    st = host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}).json()
    rnd = st["rounds"][0]
    assert not rnd["timed"] and entries(st)[0]["end_at"] is None and entries(st)[0]["close_at"] is None
    r = host.post(f"/api/matches/{code}/powerups", json={"kind": "extra"})
    assert r.status_code == 400 and "Senza tempo" in r.json()["detail"]
    clock.advance(5 * 3600)
    main.tick_all()
    assert host.get(f"/api/matches/{code}").json()["rounds"][0]["status"] == "sculpting"
    upload(host, code, 1, jpeg)
    assert upload(guest, code, 1, jpeg).json()["rounds"][0]["status"] == "judging"


def test_rush_rule(app_env, jpeg, clock):
    from app import main

    client, _ = app_env
    settings = {"judge": "voto", "timer": "nessuno", "rush": True, "rush_after": 2, "rush_minutes": 3}
    code, seats = setup_match(client, settings, players=4)
    host, a, b, c = seats
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"})
    st = upload(host, code, 1, jpeg).json()
    assert st["rounds"][0]["rush_end_at"] is None
    start = clock.t
    st = upload(a, code, 1, jpeg).json()
    rush = st["rounds"][0]["rush_end_at"]
    assert rush == start + 180
    assert entries(st)[2]["close_at"] == rush + 60 and entries(st)[2]["deadline"] == rush
    clock.advance(200)  # rincorsa finita, nel minuto per la foto
    assert upload(b, code, 1, jpeg).status_code == 200
    clock.advance(60)
    assert upload(c, code, 1, jpeg).status_code == 400
    main.tick_all()
    st = host.get(f"/api/matches/{code}").json()
    assert st["rounds"][0]["status"] == "judging"
    assert st["rounds"][0]["votes"]["targets"] == [1, 2]


def test_nobody_delivers_scores_zero(app_env, clock):
    from app import main

    client, _ = app_env
    code, (host, guest) = setup_match(client, {"judge": "voto", "timer": "rigido", "rounds": 2})
    host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    clock.advance(17 * 60)
    main.tick_all()
    st = host.get(f"/api/matches/{code}").json()
    assert st["rounds"][0]["status"] == "done" and st["status"] == "ready"
    assert all(e["points"] == 0 for e in st["rounds"][0]["entries"])


# ── giudice AI ────────────────────────────────────────────────────────────────


def test_ai_judge(app_env, jpeg):
    client, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    calls = []

    def fake(**kw):
        calls.append(kw)
        return {
            "entries": {"0": {"score": 7.0, "comment": "Bella forma"}, "1": {"score": 9.0, "comment": "Identico"},
                        "2": {"score": 4.0, "comment": "Coraggioso"}},
            "verdict": "Vince Giulia",
        }

    mp.setattr(judge, "judge", fake)
    code, seats = setup_match(client, {"judge": "ai"}, players=3)
    seats[0].post(f"/api/matches/{code}/rounds", json={"difficulty": "difficile"})
    for p in seats:
        upload(p, code, 1, jpeg)
    st = seats[0].get(f"/api/matches/{code}").json()
    rnd = st["rounds"][0]
    assert len(calls) == 1 and calls[0]["reference"]
    assert [e["name"] for e in calls[0]["entries"]] == ["Daniele", "Giulia", "Marco"]
    assert rnd["status"] == "done"
    e = entries(st)
    assert (e[0]["points"], e[1]["points"], e[2]["points"]) == (14.0, 18.0, 8.0)
    assert rnd["ai"]["result"]["verdict"] == "Vince Giulia"


def test_ai_failure_falls_back_to_votes(app_env, jpeg):
    client, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")

    def boom(**kw):
        raise RuntimeError("rete giù")

    mp.setattr(judge, "judge", boom)
    code, seats = setup_match(client, {"judge": "ai"})
    seats[0].post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
    for p in seats:
        upload(p, code, 1, jpeg)
    rnd = seats[0].get(f"/api/matches/{code}").json()["rounds"][0]
    assert rnd["status"] == "judging" and rnd["ai"]["status"] == "failed"
    assert rnd["votes"]["needed"]
    st = vote_all(code, seats, 1, lambda i, j: 5)
    assert st["rounds"][0]["status"] == "done"


def test_handicap_goes_to_leader(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(
        client, {"judge": "voto", "handicap": "leader", "memory": False, "rounds": 3}, players=3
    )
    play_round(code, seats, jpeg, value_for=lambda i, j: 9 if j == 2 else 2)
    st = seats[0].post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"}).json()
    hc = {e["seat"]: e["handicap"] for e in st["rounds"][1]["entries"]}
    assert hc[2] and not hc[0] and not hc[1]


# ── chi vede cosa ─────────────────────────────────────────────────────────────


def test_only_players_see_match_and_gallery(app_env, jpeg):
    client, _ = app_env
    code, seats = setup_match(client, {"judge": "voto", "rounds": 1})
    outsider = new_player(client, "altro@example.com", "Altro")
    other_guest = new_player(client, "amico@example.com", "Amico")
    other_code = outsider.post("/api/matches", json={"settings": {"judge": "voto", "rounds": 1}}).json()["code"]
    other_guest.post(f"/api/matches/{other_code}/join")
    # in sala d'attesa la partita si vede (serve per entrare dal link)
    assert seats[0].get(f"/api/matches/{other_code}").status_code == 200
    play_round(code, seats, jpeg)
    play_round(other_code, [outsider, other_guest], jpeg)
    assert seats[0].get(f"/api/matches/{other_code}").status_code == 403
    assert outsider.get(f"/api/matches/{code}").status_code == 403
    assert [m["code"] for m in seats[0].get("/api/gallery").json()["matches"]] == [code]
    assert [m["code"] for m in outsider.get("/api/gallery").json()["matches"]] == [other_code]


def test_websocket(app_env):
    client, _ = app_env
    # il client principale (quello con il loop dei WebSocket) è un invitato
    host = new_player(client, "dani@example.com", "Daniele")
    code = host.post("/api/matches", json={}).json()["code"]
    login(client, "giulia@example.com", "Giulia")
    client.post(f"/api/matches/{code}/join")
    with client.websocket_connect(f"/api/ws/{code}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state" and msg["state"]["you"] == 1
        assert msg["state"]["players"][1]["online"]
        host.post(f"/api/matches/{code}/rounds", json={"difficulty": "facile"})
        msg = ws.receive_json()
        assert msg["state"]["status"] == "playing"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_websocket_refuses_outsiders(app_env):
    client, _ = app_env
    code, seats = setup_match(client)
    seats[0].post(f"/api/matches/{code}/rounds", json={})
    client.post("/api/auth/logout")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/ws/{code}") as ws:
            ws.receive_json()
    assert exc.value.code == 4403


# ── migrazione dalla versione a due ───────────────────────────────────────────


def test_old_two_player_matches_are_migrated(tmp_path, monkeypatch):
    """Una partita salvata con le colonne host_*/guest_* diventa due giocatori
    con le loro consegne, voti e risultato dell'AI."""
    import sqlite3

    from app import config as cfg, db
    from app.models import Entry, Match, Player

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    path = tmp_path / "old.db"
    db.init(f"sqlite:///{path}")
    con = sqlite3.connect(path)
    con.execute("DELETE FROM players")
    con.execute("INSERT INTO users (id, email, name, created_at) VALUES (1, 'a@x.it', 'Dani', 0), (2, 'b@x.it', 'Giu', 0)")
    con.execute(
        "INSERT INTO matches (id, code, created_at, finished_at, status, settings, host_user_id, guest_user_id,"
        " host_name, guest_name, host_token, powerups) VALUES (1, 'ABCD', 0, 10, 'finished',"
        " '{\"rounds\": 1, \"judge\": \"entrambi\", \"theme\": \"misto\", \"minutes\": {\"facile\": 15, \"media\": 25, \"difficile\": 40}}',"
        " 1, 2, 'Dani', 'Giu', 't', '{\"host\": {\"extra\": false, \"sabotage\": true, \"reroll\": true}}')"
    )
    con.execute(
        "INSERT INTO rounds (id, match_id, number, difficulty, theme, subject, subject_key, memory, starts_at,"
        " duration_s, host_delta_s, guest_delta_s, status, host_photo, guest_photo, events, host_vote, guest_vote,"
        " ai_status, ai_result, host_score, guest_score, host_points, guest_points) VALUES (1, 1, 1, 'facile', 'cibo',"
        " 'Mela', 'facile:mela', 0, 0, 900, 120, 0, 'done', 'h.jpg', 'g.jpg',"
        " '[{\"by\": \"host\", \"kind\": \"sabotage\", \"at\": 1}]', 6, 8, 'done',"
        " '{\"host\": {\"score\": 7, \"comment\": \"ok\"}, \"guest\": {\"score\": 5, \"comment\": \"no\"}, \"verdict\": \"v\"}',"
        " 7.5, 5.5, 7.5, 5.5)"
    )
    con.commit()
    con.close()

    db.init(f"sqlite:///{path}")
    db.init(f"sqlite:///{path}")  # la seconda volta non deve duplicare niente
    with db.session_scope() as s:
        m = s.get(Match, 1)
        assert [(p.seat, p.user_id, p.name) for p in m.players] == [(0, 1, "Dani"), (1, 2, "Giu")]
        assert m.players[0].powerups == {"extra": False, "sabotage": True, "reroll": True}
        r = m.rounds[0]
        assert [(e.seat, e.photo, e.points, e.delta_s) for e in r.entries] == [
            (0, "h.jpg", 7.5, 120), (1, "g.jpg", 5.5, 0)
        ]
        assert r.votes == {"0": {"1": 6}, "1": {"0": 8}}
        assert r.ai_result["entries"]["1"]["score"] == 5
        assert r.events[0]["by"] == 0 and r.events[0]["target"] == 1
        assert s.query(Entry).count() == 2 and s.query(Player).count() == 2
        assert game.winners(m) == [0]


# ── impostazioni e giudice ────────────────────────────────────────────────────


def test_settings_are_clamped():
    s = game.clean_settings(
        {"rounds": 99, "judge": "ai", "minutes": {"facile": 0}, "theme": "boh", "timer": "boh",
         "rush_after": 50, "rush_minutes": 0}
    )
    assert s["rounds"] == 10 and s["minutes"]["facile"] == 1 and s["theme"] == "misto"
    assert s["judge"] == "voto"  # niente chiave → niente AI
    assert s["timer"] == "libero" and s["rush_after"] == 7 and s["rush_minutes"] == 1


def test_judge_parse_fallback():
    assert judge._parse('```json\n{"A": 1}\n```') == {"A": 1}


def test_judge_request_and_mapping(app_env, jpeg):
    """Il giudice manda reference + N foto a OpenRouter e rimappa le lettere sui posti."""
    import json as _json
    import random

    import httpx

    from app import media

    _, mp = app_env
    mp.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    names = [media.save_image(jpeg(), "x") for _ in range(4)]
    entries_in = [{"seat": i, "name": n, "photo": names[i + 1]} for i, n in enumerate(["Dani", "Giu", "Max"])]
    order = list(entries_in)
    random.Random(0).shuffle(order)
    sent = {}

    def fake_post(url, **kw):
        sent.update(kw["json"], url=url, auth=kw["headers"]["Authorization"])
        body = {
            "creations": [
                {"label": "A", "score": 3, "comment": "a"},
                {"label": "B", "score": 11, "comment": "b"},
                {"label": "C", "score": 6.25, "comment": "c"},
            ],
            "verdict": "v",
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(body)}}]})

    mp.setattr(httpx, "post", fake_post)
    out = judge.judge("Mela", "facile", names[0], entries_in, rng=random.Random(0))
    assert sent["url"].endswith("/chat/completions") and sent["auth"] == "Bearer sk-or-test"
    parts = sent["messages"][1]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 4
    expected = {"A": 3.0, "B": 10.0, "C": 6.2}
    for label, e in zip("ABC", order):
        assert out["entries"][str(e["seat"])]["score"] == expected[label]
    assert out["verdict"] == "v"


def test_judge_missing_creation_fails(app_env, jpeg, monkeypatch):
    import json as _json

    import httpx

    from app import media

    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    photo = media.save_image(jpeg(), "x")
    body = {"creations": [{"label": "A", "score": 3, "comment": "a"}], "verdict": "v"}
    monkeypatch.setattr(
        httpx, "post",
        lambda url, **kw: httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(body)}}]}),
    )
    with pytest.raises(ValueError):
        judge.judge("Mela", "facile", None, [{"seat": 0, "name": "A", "photo": photo},
                                             {"seat": 1, "name": "B", "photo": photo}])
