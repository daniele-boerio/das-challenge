# Sfida DAS — note per chi ci lavora

Gioco a due: partita con codice di 4 lettere, timer condiviso, reference pescata a caso,
foto delle creazioni, voto reciproco o giudice AI (OpenRouter). Vedi README.md.

## Struttura

- `backend/app/game.py` — **tutte le regole**: stati, round, power-up, voti, punteggi, e
  `view()`, cioè cosa vede ciascun giocatore. Le mutazioni si fanno con `game.LOCK` preso.
- `backend/app/main.py` — rotte FastAPI (tutte `def`, tranne il WebSocket) sotto `/api`.
- `backend/app/realtime.py` — stanze WebSocket; `rooms.notify(code)` da qualunque thread
  rimanda lo stato a tutti i collegati, ciascuno con la sua vista.
- `backend/app/subjects.py` — catalogo dei soggetti per difficoltà e tema, handicap.
- `backend/app/references.py` — Openverse → Wikimedia Commons, foto salvata in locale con attribuzione.
- `backend/app/judge.py` — giudice AI via OpenRouter (`/chat/completions`, JSON schema).
- `frontend/src/pages/Match.tsx` — tutta la partita (lobby, round, giudizio, risultato, finale).
- `backend/app/auth.py` — accesso con mail + codice OTP, sessione senza scadenza in cookie httpOnly.
- `frontend/src/api.ts` — tutte le chiamate (il cookie di sessione parte da solo, anche sul WebSocket).
- `frontend/src/pages/Login.tsx` — mail → codice → nome; l'app intera sta dietro questo cancello.
- `frontend/src/index.css` — un solo foglio, variabili in `:root`.

## Regole da non rompere

- Il tempo lo decide il server: `starts_at`/`end_at` sono epoch, il client li confronta con
  `server_now` + il suo scarto. Il tempo scaduto non blocca la consegna (fair play).
- La foto dell'avversario e i voti restano nascosti finché non hanno consegnato/votato entrambi;
  il risultato dell'AI si mostra solo a round chiuso, per non influenzare il voto.
- Se il giudice AI fallisce o resta appeso, il round passa al voto (`ai_failed`, `heal`):
  la partita non deve mai bloccarsi.
- Chi gioca è l'account (`host_user_id`/`guest_user_id`). Una partita la vedono solo i due
  giocatori (`check_can_view`); gli altri solo finché il posto dell'avversario è libero.
  La galleria mostra solo le partite dell'utente collegato.
- Nessun segreto nel repo: `OPENROUTER_API_KEY` e le `SMTP_*` solo nelle variabili di Coolify.
- Lo schema DB è creato con `create_all`; le colonne nuove di tabelle esistenti vanno in
  `db._NEW_COLUMNS`. Se una colonna esistente cambia, introdurre Alembic.

## Comandi

```bash
cd backend && python -m pytest -q
cd frontend && npm run build   # tsc + vite
```
