from flask import Flask, Response
import random
import requests
import sqlite3
import os
from urllib.parse import unquote

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

POKEAPI = "https://pokeapi.co/api/v2/pokemon?limit=1025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "pokemon.db")

_cache = None

# Pesos de encontro
RARITY_WEIGHTS = [
    ("comum", 55),
    ("incomum", 25),
    ("raro", 13),
    ("lendario", 6),
    ("mitico", 1),
]

# Chance de captura
CAPTURE_CHANCES = {
    "comum": 0.78,
    "incomum": 0.60,
    "raro": 0.42,
    "lendario": 0.20,
    "mitico": 0.08,
}

RARITY_LABEL = {
    "comum": "🟢 COMUM",
    "incomum": "🔵 INCOMUM",
    "raro": "🟣 RARO",
    "lendario": "🟡 LENDÁRIO",
    "mitico": "🔴 MÍTICO",
}


# ============================================================
# BANCO DE DADOS
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trainers (
            username TEXT PRIMARY KEY,
            captures INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            battles INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection (
            username TEXT NOT NULL,
            pokemon TEXT NOT NULL,
            rarity TEXT NOT NULL,
            amount INTEGER DEFAULT 1,
            PRIMARY KEY (username, pokemon)
        )
    """)

    conn.commit()
    conn.close()


init_db()


def ensure_trainer(username):
    username = username.strip()

    if not username:
        username = "Treinador"

    conn = get_db()

    conn.execute(
        """
        INSERT OR IGNORE INTO trainers
        (username, captures, wins, losses, battles)
        VALUES (?, 0, 0, 0, 0)
        """,
        (username,)
    )

    conn.commit()
    conn.close()


# ============================================================
# POKÉAPI
# ============================================================

def load_species():
    global _cache

    if _cache is not None:
        return _cache

    response = requests.get(POKEAPI, timeout=20)
    response.raise_for_status()

    data = response.json()
    results = data["results"]

    enriched = []

    for item in results:
        name = item["name"].replace("-", " ")

        try:
            pokemon_id = int(
                item["url"].rstrip("/").split("/")[-1]
            )
        except Exception:
            continue

        # Distribuição determinística de raridade.
        # Isso evita centenas de requisições à PokéAPI.
        if pokemon_id % 100 == 0:
            rarity = "mitico"
        elif pokemon_id % 50 == 0:
            rarity = "lendario"
        elif pokemon_id % 10 < 2:
            rarity = "raro"
        elif pokemon_id % 10 < 5:
            rarity = "incomum"
        else:
            rarity = "comum"

        enriched.append((name, rarity))

    _cache = enriched

    return _cache


def pick_rarity():
    names = [x[0] for x in RARITY_WEIGHTS]
    weights = [x[1] for x in RARITY_WEIGHTS]

    return random.choices(
        names,
        weights=weights,
        k=1
    )[0]


def pick_pokemon(rarity):
    all_species = load_species()

    pool = [
        name
        for name, r in all_species
        if r == rarity
    ]

    if not pool:
        pool = [
            name
            for name, r in all_species
            if r == "comum"
        ]

    return random.choice(pool)


# ============================================================
# CAPTURA
# ============================================================

def save_capture(username, pokemon, rarity):
    ensure_trainer(username)

    conn = get_db()

    conn.execute(
        """
        UPDATE trainers
        SET captures = captures + 1
        WHERE username = ?
        """,
        (username,)
    )

    conn.execute(
        """
        INSERT INTO collection
        (username, pokemon, rarity, amount)
        VALUES (?, ?, ?, 1)

        ON CONFLICT(username, pokemon)
        DO UPDATE SET amount = amount + 1
        """,
        (username, pokemon, rarity)
    )

    conn.commit()
    conn.close()


def make_result(user):
    ensure_trainer(user)

    rarity = pick_rarity()
    pokemon = pick_pokemon(rarity)

    chance = CAPTURE_CHANCES[rarity]
    roll = random.random()

    # 5% de chance de captura crítica
    critical = random.random() < 0.05

    # 22% de chance de contra-ataque
    counter = random.random() < 0.22

    captured = False

    if critical:
        captured = True
        outcome = (
            f"💥 CAPTURA CRÍTICA! "
            f"{user} capturou {pokemon}!"
        )

    elif roll < chance:
        captured = True

        if rarity == "mitico":
            outcome = (
                f"✨ INACREDITÁVEL! "
                f"{user} capturou o MÍTICO {pokemon}!"
            )

        elif rarity == "lendario":
            outcome = (
                f"🌟 LENDA CAPTURADA! "
                f"{user} conseguiu capturar "
                f"o LENDÁRIO {pokemon}!"
            )

        elif rarity == "raro":
            outcome = (
                f"🎉 Boa! {user} capturou "
                f"o RARO {pokemon}!"
            )

        else:
            outcome = (
                f"🎉 {user} capturou {pokemon}!"
            )

    elif counter:
        outcome = (
            f"⚡ {pokemon} revidou! "
            f"{user} foi atingido!"
        )

    else:
        outcome = (
            f"😱 {pokemon} escapou da "
            f"Pokébola no último instante!"
        )

    if captured:
        save_capture(user, pokemon, rarity)

    return (
        f"{user} encontrou {pokemon}! "
        f"{RARITY_LABEL[rarity]} — {outcome}"
    )


# ============================================================
# /pokemon
# ============================================================

@app.get("/pokemon")
def pokemon():
    return Response(
        make_result("O treinador"),
        mimetype="text/plain; charset=utf-8"
    )


@app.get("/pokemon/<user>")
def pokemon_user(user):
    user = unquote(user)

    return Response(
        make_result(user),
        mimetype="text/plain; charset=utf-8"
    )


# ============================================================
# /pokemons
# ============================================================

@app.get("/pokemons/<user>")
def pokemons(user):
    user = unquote(user)

    ensure_trainer(user)

    conn = get_db()

    rows = conn.execute(
        """
        SELECT pokemon, rarity, amount
        FROM collection
        WHERE username = ?
        ORDER BY rarity, pokemon
        """,
        (user,)
    ).fetchall()

    conn.close()

    if not rows:
        return Response(
            f"🎒 {user} ainda não capturou nenhum Pokémon!",
            mimetype="text/plain; charset=utf-8"
        )

    parts = []

    for row in rows:
        label = RARITY_LABEL.get(
            row["rarity"],
            row["rarity"]
        )

        if row["amount"] > 1:
            parts.append(
                f"{row['pokemon']} x{row['amount']} "
                f"{label}"
            )
        else:
            parts.append(
                f"{row['pokemon']} {label}"
            )

    total = sum(row["amount"] for row in rows)

    result = (
        f"🎒 Coleção de {user} — "
        f"{total} Pokémon capturados: "
        + " | ".join(parts)
    )

    return Response(
        result,
        mimetype="text/plain; charset=utf-8"
    )


# ============================================================
# /perfil
# ============================================================

@app.get("/perfil/<user>")
def perfil(user):
    user = unquote(user)

    ensure_trainer(user)

    conn = get_db()

    trainer = conn.execute(
        """
        SELECT *
        FROM trainers
        WHERE username = ?
        """,
        (user,)
    ).fetchone()

    unique = conn.execute(
        """
        SELECT COUNT(*)
        FROM collection
        WHERE username = ?
        """,
        (user,)
    ).fetchone()[0]

    rare = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM collection
        WHERE username = ?
        AND rarity = 'raro'
        """,
        (user,)
    ).fetchone()[0]

    legendary = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM collection
        WHERE username = ?
        AND rarity = 'lendario'
        """,
        (user,)
    ).fetchone()[0]

    mythical = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM collection
        WHERE username = ?
        AND rarity = 'mitico'
        """,
        (user,)
    ).fetchone()[0]

    conn.close()

    result = (
        f"👤 PERFIL DE {user} | "
        f"🎒 Pokémon: {trainer['captures']} | "
        f"📖 Espécies: {unique} | "
        f"🟣 Raros: {rare} | "
        f"🟡 Lendários: {legendary} | "
        f"🔴 Míticos: {mythical} | "
        f"⚔️ Batalhas: {trainer['battles']} | "
        f"🏆 Vitórias: {trainer['wins']} | "
        f"💀 Derrotas: {trainer['losses']}"
    )

    return Response(
        result,
        mimetype="text/plain; charset=utf-8"
    )


# ============================================================
# BATALHA
# ============================================================

@app.get("/batalha/<user>/<opponent>")
def batalha(user, opponent):
    user = unquote(user)
    opponent = unquote(opponent)

    opponent = opponent.lstrip("@")

    if user.lower() == opponent.lower():
        return Response(
            "⚠️ Você não pode batalhar contra si mesmo!",
            mimetype="text/plain; charset=utf-8"
        )

    ensure_trainer(user)
    ensure_trainer(opponent)

    conn = get_db()

    user_pokemon = conn.execute(
        """
        SELECT pokemon, rarity
        FROM collection
        WHERE username = ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (user,)
    ).fetchone()

    opponent_pokemon = conn.execute(
        """
        SELECT pokemon, rarity
        FROM collection
        WHERE username = ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (opponent,)
    ).fetchone()

    conn.close()

    if not user_pokemon:
        return Response(
            f"⚠️ {user} ainda não tem Pokémon "
            f"para batalhar!",
            mimetype="text/plain; charset=utf-8"
        )

    if not opponent_pokemon:
        return Response(
            f"⚠️ {opponent} ainda não tem Pokémon "
            f"para batalhar!",
            mimetype="text/plain; charset=utf-8"
        )

    # Pequena vantagem baseada na raridade
    rarity_power = {
        "comum": 1,
        "incomum": 2,
        "raro": 3,
        "lendario": 5,
        "mitico": 7,
    }

    user_power = (
        rarity_power[user_pokemon["rarity"]]
        + random.randint(1, 10)
    )

    opponent_power = (
        rarity_power[opponent_pokemon["rarity"]]
        + random.randint(1, 10)
    )

    if user_power >= opponent_power:
        winner = user
        loser = opponent
        winner_pokemon = user_pokemon["pokemon"]
        loser_pokemon = opponent_pokemon["pokemon"]
    else:
        winner = opponent
        loser = user
        winner_pokemon = opponent_pokemon["pokemon"]
        loser_pokemon = user_pokemon["pokemon"]

    conn = get_db()

    conn.execute(
        """
        UPDATE trainers
        SET battles = battles + 1
        WHERE username IN (?, ?)
        """,
        (user, opponent)
    )

    conn.execute(
        """
        UPDATE trainers
        SET wins = wins + 1
        WHERE username = ?
        """,
        (winner,)
    )

    conn.execute(
        """
        UPDATE trainers
        SET losses = losses + 1
        WHERE username = ?
        """,
        (loser,)
    )

    conn.commit()
    conn.close()

    result = (
        f"⚔️ BATALHA! {user} "
        f"({user_pokemon['pokemon']}) vs "
        f"{opponent} ({opponent_pokemon['pokemon']}) — "
        f"🏆 {winner} venceu com {winner_pokemon}! "
        f"{loser_pokemon} foi derrotado!"
    )

    return Response(
        result,
        mimetype="text/plain; charset=utf-8"
    )


# ============================================================
# /top
# ============================================================

@app.get("/top")
def top():
    conn = get_db()

    rows = conn.execute(
        """
        SELECT username, captures, wins
        FROM trainers
        ORDER BY captures DESC, wins DESC
        LIMIT 10
        """
    ).fetchall()

    conn.close()

    if not rows:
        return Response(
            "🏆 Ainda não existem treinadores no ranking!",
            mimetype="text/plain; charset=utf-8"
        )

    ranking = []

    for i, row in enumerate(rows, start=1):
        ranking.append(
            f"{i}º {row['username']} "
            f"— 🎒 {row['captures']} Pokémon "
            f"— 🏆 {row['wins']} vitórias"
        )

    result = "🏆 TOP TREINADORES | " + " | ".join(ranking)

    return Response(
        result,
        mimetype="text/plain; charset=utf-8"
    )


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    return (
        "Pokemon chatbot API online. "
        "Comandos: pokemon, pokemons, perfil, "
        "batalha e top."
    )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
    )
