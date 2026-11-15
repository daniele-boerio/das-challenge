# Sfida DAS 🏺

Una webapp per sfidarsi con il DAS (la pasta da modellare che si asciuga all'aria), da 2 a 8
giocatori: l'app pesca una reference, parte un timer condiviso, ognuno scolpisce sul proprio
tavolo e alla fine carica la foto. Si vota a vicenda oppure decide un giudice AI. Vince chi fa
più punti.

## Come si gioca

0. Si entra con la mail: arriva un codice di 6 cifre, la prima volta si sceglie il nome, e poi
   si resta dentro per sempre su quel dispositivo.
1. Chi crea la sfida sceglie le regole e manda il link (o il codice di 4 lettere).
2. Gli altri entrano dal link, ciascuno dal suo telefono, fino a 8 giocatori. Si entra anche
   a partita cominciata: chi arriva a metà guarda il round in corso e gioca dal successivo. A
   partita finita non si entra più, e la vedono solo i giocatori.
3. A ogni round chi ha creato la partita sceglie la difficoltà: **facile ×1**, **media ×1,5**,
   **difficile ×2** (oppure casuale). Dopo un «3, 2, 1» compare la reference e parte il timer.
4. Quando hai finito, o allo scadere, fotografi la tua creazione e la consegni.
5. Si vede il confronto affiancato alla reference e si giudica:
   - **voto fra voi**: ognuno dà da 0 a 10 alle creazioni di tutti gli altri, il punteggio è la
     media dei voti ricevuti, voti segreti fino alla fine (chi ha creato la partita può chiudere
     la votazione se qualcuno sparisce);
   - **giudice AI**: un modello via OpenRouter confronta tutte le foto con la reference e commenta;
   - **entrambi**: media fra voto e AI.
6. Punti del round = voto × moltiplicatore. Alla fine c'è la classifica e la rivincita a un tocco.

### Il tempo

- **Timer libero** (default): allo scadere si può continuare e consegnare lo stesso.
- **Timer rigido**: allo scadere c'è 1 minuto per fotografare, poi le consegne si chiudono e chi
  non ha consegnato prende 0 in quel round (ma vota gli altri).
- **Senza tempo**: niente timer, il round finisce quando hanno consegnato tutti.
- **Gli ultimi rincorrono** (facoltativa, con qualsiasi timer): quando N giocatori hanno
  consegnato, chi manca ha M minuti per finire; questa scadenza è sempre rigida.

### Extra

- **Power-up**, uno a testa per partita: *+2 minuti*, *−1 minuto a un avversario a scelta*,
  *cambia soggetto* (nei primi 2 minuti, fa ripartire il round per tutti). Senza tempo resta solo
  il cambio soggetto.
- **Handicap**: a chi è in testa, oppure a sorpresa (mano non dominante, occhi chiusi per 30 secondi…).
- **Round a memoria**: ogni tanto la reference sparisce dopo 30 secondi.
- **Temi**: misto, animali, cibo, oggetti di casa, natura, fantasy.
- **Galleria**: le *tue* sfide finite con reference e foto, le tue vittorie e il testa a testa
  con ogni avversario (in quante sfide giocate insieme hai fatto più punti tu o lui).

## Chi può usare l'AI

L'AI costa a chi ha messo la chiave, quindi si accende solo nelle partite in cui gioca un account
elencato in `AI_EMAILS` (mail separate da virgole, nelle variabili di Coolify). Nelle altre partite
si vota a vicenda e le reference si cercano su Openverse e Commons senza nessun modello.

## Da dove vengono le reference

La reference non è il soggetto vero ma **una scultura in pasta da modellare** di quel soggetto
(DAS, pongo, polymer clay, plastilina, fimo): è quella che ha senso provare a rifare.
Il catalogo dei soggetti (`backend/app/subjects.py`) è scelto a mano perché sia fattibile col DAS.

Con la chiave OpenRouter la foto si **genera** (`backend/app/imagegen.py`): una scultura fatta a
mano del soggetto, in DAS bianco o in paste colorate secondo l'impostazione, più semplice o più
dettagliata secondo la difficoltà. Costa circa mezzo centesimo a foto col modello di default
(`IMAGE_MODEL`, di default `openai/gpt-image-2`; se non è nel listino si prende un
altro modello di immagini economico). `IMAGE_AI=false` la spegne.

Se la generazione fallisce, si cerca «polymer clay …», «clay …», «plasticine …» su
[Openverse](https://openverse.org) (immagini Creative Commons) e poi su
[Wikimedia Commons](https://commons.wikimedia.org), e si tengono solo i risultati che nel titolo,
nei tag o nelle categorie dicono di essere di pasta da modellare. Se c'è la chiave OpenRouter, un
modello guarda le miniature e sceglie quella che è davvero una scultura del soggetto, singola e ben
visibile (`REFERENCE_AI=false` per spegnerlo, `REFERENCE_MODEL` per usare un modello diverso dal
giudice; di default sceglie il Claude Sonnet più recente, che è veloce). Le reference si preparano in
anticipo, una per difficoltà, appena la partita esiste e mentre si scolpisce: «Via al round!» parte
subito. Se non si trova nessuna scultura il round parte col solo nome del soggetto.
La foto si salva in locale con la sua attribuzione, che compare sotto l'immagine come chiede la licenza.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy su SQLite, WebSocket per il tempo reale
- **Frontend:** React 19, TypeScript, Vite, lucide-react
- **Deploy:** Docker Compose su Coolify, nginx davanti (serve la SPA e inoltra `/api` e il WebSocket)

## In locale

```bash
# backend
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (altro terminale)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

## Variabili d'ambiente (Coolify)

| Variabile | A cosa serve |
| --- | --- |
| `OPENROUTER_API_KEY` | Accende il giudice AI. Senza, si gioca solo col voto reciproco. |
| `AI_MODEL` | Slug OpenRouter del modello (default `anthropic/claude-opus-4-8`). |
| `REFERENCE_AI`, `REFERENCE_MODEL` | Il modello che sceglie la scultura fra le miniature (acceso di default se c'è la chiave; modello vuoto = `AI_MODEL`). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Spedizione dei codici di accesso (Gmail: `smtp.gmail.com`, 587, la tua mail, una password per le app). Senza `SMTP_HOST` il codice compare nei log del backend. |
| `ALLOWED_EMAILS` | Facoltativo: elenco di mail separate da virgola che possono entrare. Vuoto = chiunque. |
| `COOKIE_SECURE` | `true` in produzione (default nel compose), `false` in locale su http. |

Le chiavi stanno **solo** nelle variabili di Coolify, mai nel repository. Database e foto vivono
nel volume `das-data` (`/data` nel container): è l'unica cosa da mettere nei backup.
