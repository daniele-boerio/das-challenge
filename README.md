# Sfida DAS 🏺

Una webapp per sfidarsi a coppie con il DAS (la pasta da modellare che si asciuga all'aria):
l'app pesca una reference, parte un timer condiviso, ognuno scolpisce sul proprio tavolo e
alla fine carica la foto. Si vota a vicenda oppure decide un giudice AI. Vince chi fa più punti.

## Come si gioca

1. Chi crea la sfida sceglie le regole e manda il link (o il codice di 4 lettere).
2. L'altro entra dal link, dal suo telefono.
3. A ogni round chi ha creato la partita sceglie la difficoltà: **facile ×1**, **media ×1,5**,
   **difficile ×2** (oppure casuale). Dopo un «3, 2, 1» compare la reference e parte il timer.
4. Quando hai finito, o allo scadere, fotografi la tua creazione e la consegni.
5. Si vede il confronto affiancato alla reference e si giudica:
   - **voto reciproco**: ognuno dà da 0 a 10 alla creazione dell'altro, voti segreti fino alla fine;
   - **giudice AI**: un modello via OpenRouter confronta le foto con la reference e commenta;
   - **entrambi**: media fra voto e AI.
6. Punti del round = voto × moltiplicatore. Alla fine c'è la classifica e la rivincita a un tocco.

### Extra

- **Power-up**, uno a testa per partita: *+2 minuti*, *−1 minuto all'avversario*, *cambia soggetto*
  (nei primi 2 minuti, fa ripartire il round per tutti e due).
- **Handicap**: a chi è in testa, oppure a sorpresa (mano non dominante, occhi chiusi per 30 secondi…).
- **Round a memoria**: ogni tanto la reference sparisce dopo 30 secondi.
- **Temi**: misto, animali, cibo, oggetti di casa, natura, fantasy.
- **Galleria**: tutte le sfide finite con reference e foto, e il conto delle vittorie fra voi.

## Da dove vengono le reference

Il catalogo dei soggetti (`backend/app/subjects.py`) è scelto a mano perché sia fattibile col DAS.
Per ogni soggetto la foto si cerca su [Openverse](https://openverse.org) (immagini Creative Commons)
e, se non trova niente, su [Wikimedia Commons](https://commons.wikimedia.org). La foto si salva in
locale con la sua attribuzione, che compare sotto l'immagine come chiede la licenza.

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
| `ACCESS_CODE` | Facoltativo: serve per creare partite e vedere la galleria. Chi entra dal link non ne ha bisogno. |

Le chiavi stanno **solo** nelle variabili di Coolify, mai nel repository. Database e foto vivono
nel volume `das-data` (`/data` nel container): è l'unica cosa da mettere nei backup.
