# Sfida DAS — note per chi ci lavora

Gioco da 2 a 8: partita con codice di 4 lettere, timer condiviso, reference pescata a caso,
foto delle creazioni, voto reciproco o giudice AI (OpenRouter). Vedi README.md.

## Struttura

- `backend/app/game.py` — **tutte le regole**: stati, round, power-up, voti, punteggi, e
  `view()`, cioè cosa vede ciascun giocatore. Le mutazioni si fanno con `game.LOCK` preso.
  Ogni giocatore ha un posto (`Player.seat`, 0 = chi ha creato la partita) e in ogni round una
  `Entry` (tempo, handicap, foto, punti); i voti stanno in `Round.votes` per posto.
- `backend/app/main.py` ha anche il ticker (`tick_all`, ogni 2 s): chiude i round scaduti
  (timer rigido, rincorsa) anche se nessuno tocca niente. Nei test è spento (`TICKER`).
- `backend/app/main.py` — rotte FastAPI (tutte `def`, tranne il WebSocket) sotto `/api`.
- `backend/app/realtime.py` — stanze WebSocket; `rooms.notify(code)` da qualunque thread
  rimanda lo stato a tutti i collegati, ciascuno con la sua vista.
- `backend/app/subjects.py` — catalogo dei soggetti per difficoltà e tema, handicap.
- `backend/app/references.py` — la reference è una **scultura in pasta da modellare** del soggetto, mai il soggetto
  vero: ricerche «clay …» su Openverse → Wikimedia Commons, filtro sulle parole (`is_clay`), scelta
  del modello fra le miniature (`_ai_pick`), foto salvata in locale con attribuzione.
- `backend/app/judge.py` — giudice AI via OpenRouter (`/chat/completions`, JSON schema).
- `frontend/src/pages/Match.tsx` — tutta la partita (lobby, round, giudizio, risultato, finale).
- `backend/app/auth.py` — accesso con mail + codice OTP, sessione senza scadenza in cookie httpOnly.
- `frontend/src/api.ts` — tutte le chiamate (il cookie di sessione parte da solo, anche sul WebSocket).
- `frontend/src/pages/Login.tsx` — mail → codice → nome; l'app intera sta dietro questo cancello.
- `frontend/src/index.css` — un solo foglio, variabili in `:root`.

## Regole da non rompere

- Il tempo lo decide il server: `starts_at`/`end_at` sono epoch, il client li confronta con
  `server_now` + il suo scarto. Col timer libero il tempo scaduto non blocca la consegna.
- Le foto degli altri e i voti restano nascosti finché le consegne/il voto non sono chiusi;
  il risultato dell'AI si mostra solo a round chiuso, per non influenzare il voto.
- Se il giudice AI fallisce o resta appeso, il round passa al voto (`ai_failed`, `heal`):
  la partita non deve mai bloccarsi.
- Chi gioca è l'account (`Player.user_id`). Una partita la vedono solo i giocatori
  (`check_can_view`); gli altri solo finché ci si può entrare (sala d'attesa, non piena).
  Col primo round la partita si chiude. La galleria mostra solo le partite dell'utente collegato.
- Le scadenze rigide (`close_at`) hanno sempre `GRACE_S` in più per fotografare; il timer
  libero non chiude mai le consegne, la rincorsa sì.
- Le colonne `host_*`/`guest_*` di `matches` e `rounds` sono della versione a due: i dati
  sono passati a `players`/`entries` con `db._migrate_players` (una volta per partita). Non
  si usano più, restano perché SQLite le ha già.
- L'impostazione `colors` (default false = solo DAS bianco) decide il colore: senza, il giudice
  ignora il colore e la scelta della reference preferisce sculture bianche o monocolore che si
  riconoscono dalla forma; con, reference anche colorate e il colore conta un po' nel voto.
- Nessun segreto nel repo: `OPENROUTER_API_KEY` e le `SMTP_*` solo nelle variabili di Coolify.
- Lo schema DB è creato con `create_all`; le colonne nuove di tabelle esistenti vanno in
  `db._NEW_COLUMNS`. Se una colonna esistente cambia, introdurre Alembic.

## Comandi

```bash
cd backend && python -m pytest -q
cd frontend && npm run build   # tsc + vite
```
