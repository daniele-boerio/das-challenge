"""Il catalogo dei soggetti da scolpire.

Scelto a mano perché sia fattibile col DAS: forme piene, che stanno in piedi, con
dettagli che crescono con la difficoltà. Per ogni soggetto la `query` (in inglese)
è ciò che si cerca su Openverse / Wikimedia Commons per trovarne una foto.
"""

import random

DIFFICULTIES = ("facile", "media", "difficile")
MULTIPLIER = {"facile": 1.0, "media": 1.5, "difficile": 2.0}
DEFAULT_MINUTES = {"facile": 15, "media": 25, "difficile": 40}

THEMES = {
    "misto": "Misto",
    "animali": "Animali",
    "cibo": "Cibo",
    "oggetti": "Oggetti di casa",
    "natura": "Natura",
    "fantasy": "Fantasy e mostri",
}

# (nome italiano, query, tema)
SUBJECTS: dict[str, list[tuple[str, str, str]]] = {
    "facile": [
        ("Mela", "red apple fruit isolated", "cibo"),
        ("Pera", "pear fruit", "cibo"),
        ("Fungo", "mushroom", "natura"),
        ("Ciambella", "donut", "cibo"),
        ("Uovo nel portauovo", "egg in egg cup", "oggetti"),
        ("Tazza", "coffee mug", "oggetti"),
        ("Cactus in vaso", "cactus pot", "natura"),
        ("Sasso levigato", "smooth pebble stone", "natura"),
        ("Carota", "carrot vegetable", "cibo"),
        ("Pinguino stilizzato", "penguin figurine", "animali"),
        ("Lumaca", "snail", "animali"),
        ("Cono gelato", "ice cream cone", "cibo"),
        ("Ghianda", "acorn", "natura"),
        ("Fantasmino", "ghost figurine", "fantasy"),
        ("Pulcino", "chick bird baby", "animali"),
        ("Candela", "candle", "oggetti"),
    ],
    "media": [
        ("Gatto acciambellato", "cat sleeping curled up", "animali"),
        ("Tartaruga", "tortoise", "animali"),
        ("Gufo", "owl", "animali"),
        ("Scarpa da ginnastica", "sneaker shoe", "oggetti"),
        ("Teiera", "teapot", "oggetti"),
        ("Pigna", "pine cone", "natura"),
        ("Croissant", "croissant", "cibo"),
        ("Fetta di torta", "slice of cake", "cibo"),
        ("Rana", "frog", "animali"),
        ("Conchiglia", "seashell", "natura"),
        ("Riccio", "hedgehog", "animali"),
        ("Ninfea", "water lily flower", "natura"),
        ("Bonsai", "bonsai tree", "natura"),
        ("Draghetto cucciolo", "baby dragon figurine", "fantasy"),
        ("Robot giocattolo", "toy robot", "fantasy"),
        ("Pupazzo di neve", "snowman", "fantasy"),
        ("Hamburger", "hamburger", "cibo"),
        ("Coniglio seduto", "rabbit sitting", "animali"),
    ],
    "difficile": [
        ("Mano aperta", "open hand palm", "oggetti"),
        ("Volto di profilo", "face profile sculpture", "fantasy"),
        ("Cavallo", "horse standing", "animali"),
        ("Drago", "dragon sculpture", "fantasy"),
        ("Rosa", "rose flower", "natura"),
        ("Polpo", "octopus", "animali"),
        ("Teschio", "human skull", "fantasy"),
        ("Bicicletta", "bicycle", "oggetti"),
        ("Gatto che si stiracchia", "cat stretching", "animali"),
        ("Albero con radici", "tree roots", "natura"),
        ("Camaleonte", "chameleon", "animali"),
        ("Busto romano", "roman bust sculpture", "fantasy"),
        ("Cesto di frutta", "fruit basket", "cibo"),
        ("Piede", "human foot", "oggetti"),
        ("Granchio", "crab", "animali"),
        ("Lampada da tavolo", "desk lamp", "oggetti"),
        ("Torta a piani", "tiered wedding cake", "cibo"),
        ("Pavone", "peacock", "animali"),
    ],
}

HANDICAPS = [
    "Solo con la mano non dominante",
    "Occhi chiusi per i primi 30 secondi",
    "Niente attrezzi: solo dita",
    "Una mano dietro la schiena per i primi 3 minuti",
    "Usi al massimo una pallina di DAS grande come una noce",
    "Dopo il primo minuto non puoi più guardare la reference",
    "Lavori in piedi per tutto il round",
    "Ogni 5 minuti passi 30 secondi con gli occhi chiusi",
]


def key(difficulty: str, name: str) -> str:
    return f"{difficulty}:{name}"


def pick(difficulty: str, theme: str, exclude: set[str], rng: random.Random | None = None):
    """Un soggetto della difficoltà e del tema dati, che non sia già uscito.
    Se il tema è esaurito si allarga a tutti; se è esaurito tutto, si ricomincia."""
    rng = rng or random
    pool = SUBJECTS[difficulty]
    themed = [s for s in pool if theme == "misto" or s[2] == theme]
    for candidates in (themed, pool):
        fresh = [s for s in candidates if key(difficulty, s[0]) not in exclude]
        if fresh:
            return rng.choice(fresh)
    return rng.choice(themed or pool)
