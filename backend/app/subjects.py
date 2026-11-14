"""Il catalogo dei soggetti da scolpire.

Scelto a mano perché sia fattibile col DAS: forme piene, che stanno in piedi, con
dettagli che crescono con la difficoltà. Per ogni soggetto la `query` è il nome
inglese, corto: `references` ci aggiunge «clay», «polymer clay»… perché la reference
dev'essere una scultura in pasta da modellare, non il soggetto vero.
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
        ("Mela", "apple", "cibo"),
        ("Pera", "pear", "cibo"),
        ("Fungo", "mushroom", "natura"),
        ("Ciambella", "donut", "cibo"),
        ("Uovo nel portauovo", "egg cup", "oggetti"),
        ("Tazza", "mug", "oggetti"),
        ("Cactus in vaso", "cactus", "natura"),
        ("Sasso levigato", "stone", "natura"),
        ("Carota", "carrot", "cibo"),
        ("Pinguino stilizzato", "penguin", "animali"),
        ("Lumaca", "snail", "animali"),
        ("Cono gelato", "ice cream cone", "cibo"),
        ("Ghianda", "acorn", "natura"),
        ("Fantasmino", "ghost", "fantasy"),
        ("Pulcino", "chick", "animali"),
        ("Candela", "candle", "oggetti"),
    ],
    "media": [
        ("Gatto acciambellato", "sleeping cat", "animali"),
        ("Tartaruga", "tortoise", "animali"),
        ("Gufo", "owl", "animali"),
        ("Scarpa da ginnastica", "sneaker", "oggetti"),
        ("Teiera", "teapot", "oggetti"),
        ("Pigna", "pine cone", "natura"),
        ("Croissant", "croissant", "cibo"),
        ("Fetta di torta", "cake slice", "cibo"),
        ("Rana", "frog", "animali"),
        ("Conchiglia", "seashell", "natura"),
        ("Riccio", "hedgehog", "animali"),
        ("Ninfea", "water lily", "natura"),
        ("Bonsai", "bonsai", "natura"),
        ("Draghetto cucciolo", "baby dragon", "fantasy"),
        ("Robot giocattolo", "toy robot", "fantasy"),
        ("Pupazzo di neve", "snowman", "fantasy"),
        ("Hamburger", "hamburger", "cibo"),
        ("Coniglio seduto", "bunny", "animali"),
    ],
    "difficile": [
        ("Mano aperta", "hand", "oggetti"),
        ("Volto di profilo", "face", "fantasy"),
        ("Cavallo", "horse", "animali"),
        ("Drago", "dragon", "fantasy"),
        ("Rosa", "rose", "natura"),
        ("Polpo", "octopus", "animali"),
        ("Teschio", "skull", "fantasy"),
        ("Bicicletta", "bicycle", "oggetti"),
        ("Gatto che si stiracchia", "cat", "animali"),
        ("Albero con radici", "tree", "natura"),
        ("Camaleonte", "chameleon", "animali"),
        ("Busto romano", "bust", "fantasy"),
        ("Cesto di frutta", "fruit basket", "cibo"),
        ("Piede", "foot", "oggetti"),
        ("Granchio", "crab", "animali"),
        ("Lampada da tavolo", "lamp", "oggetti"),
        ("Torta a piani", "wedding cake", "cibo"),
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
