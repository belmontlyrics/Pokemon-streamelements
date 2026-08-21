from flask import Flask, Response
import random
import requests
import os
from urllib.parse import unquote
from supabase import create_client

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

POKEAPI = "https://pokeapi.co/api/v2/pokemon?limit=1025"

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

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
# BANCO DE DADOS — SUPABASE
# ============================================================

def ensure_trainer(username):
    username = username.strip()

    if not username:
        username = "Treinador"

    existing = (
        supabase.table("trainers")
        .select("username")
        .eq("username", username)
        .execute()
    )

    if not existing.data:
        supabase.table("trainers").insert({
            "username": username,
            "capture": 0,
            "wins": 0,
            "losses": 0,
            "battles": 0
        }).execute()


def save_capture(username, pokemon, rarity):
    ensure_trainer(username)

    trainer = (
        supabase.table("trainers")
        .select("capture")
        .eq("username", username)
        .single()
        .execute()
    )

    current_capture = trainer.data["capture"] or 0

    supabase.table("trainers").update({
        "capture": current_capture + 1
    }).eq(
        "username", username
    ).execute()

    existing = (
        supabase.table("collection")
        .select("amount")
        .eq("username", username)
        .eq("pokemon", pokemon)
        .execute()
    )

    if existing.data:
        current_amount = existing.data[0]["amount"] or 0

        supabase.table("collection").update({
            "amount": current_amount + 1
        }).eq(
            "username", username
        ).eq(
            "pokemon", pokemon
        ).execute()

    else:
        supabase.table("collection").insert({
            "username": username,
            "pokemon": pokemon,
            "rarity": rarity,
            "amount": 1
        }).execute()


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

def make_result(user):
    ensure_trainer(user)

    rarity = pick_rarity()
    pokemon = pick_pokemon(rarity)

    chance = CAPTURE_CHANCES[rarity]
    roll = random.random()

    critical = random.random() < 0.05
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

    response = (
        supabase.table("collection")
        .select("pokemon, rarity, amount")
        .eq("username", user)
        .execute()
    )

    rows = response.data

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

    trainer_response = (
        supabase.table("trainers")
        .select("*")
        .eq("username", user)
        .single()
        .execute()
    )

    trainer = trainer_response.data

    collection_response = (
        supabase.table("collection")
        .select("pokemon, rarity, amount")
        .eq("username", user)
        .execute()
    )

    rows = collection_response.data

    unique = len(rows)

    rare = sum(
        row["amount"]
        for row in rows
        if row["rarity"] == "raro"
    )

    legendary = sum(
        row["amount"]
        for row in rows
        if row["rarity"] == "lendario"
    )

    mythical = sum(
        row["amount"]
        for row in rows
        if row["rarity"] == "mitico"
    )

    result = (
        f"👤 PERFIL DE {user} | "
        f"🎒 Pokémon: {trainer['capture']} | "
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

    user_response = (
        supabase.table("collection")
        .select("pokemon, rarity")
        .eq("username", user)
        .execute()
    )

    opponent_response = (
        supabase.table("collection")
        .select("pokemon, rarity")
        .eq("username", opponent)
        .execute()
    )

    user_collection = user_response.data
    opponent_collection = opponent_response.data

    if not user_collection:
        return Response(
            f"⚠️ {user} ainda não tem Pokémon "
            f"para batalhar!",
            mimetype="text/plain; charset=utf-8"
        )

    if not opponent_collection:
        return Response(
            f"⚠️ {opponent} ainda não tem Pokémon "
            f"para batalhar!",
            mimetype="text/plain; charset=utf-8"
        )

    user_pokemon = random.choice(user_collection)
    opponent_pokemon = random.choice(opponent_collection)

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

    user_trainer = (
        supabase.table("trainers")
        .select("battles")
        .eq("username", user)
        .single()
        .execute()
    )

    opponent_trainer = (
        supabase.table("trainers")
        .select("battles")
        .eq("username", opponent)
        .single()
        .execute()
    )

    supabase.table("trainers").update({
        "battles": (user_trainer.data["battles"] or 0) + 1
    }).eq(
        "username", user
    ).execute()

    supabase.table("trainers").update({
        "battles": (opponent_trainer.data["battles"] or 0) + 1
    }).eq(
        "username", opponent
    ).execute()

    winner_data = (
        supabase.table("trainers")
        .select("wins")
        .eq("username", winner)
        .single()
        .execute()
    )

    loser_data = (
        supabase.table("trainers")
        .select("losses")
        .eq("username", loser)
        .single()
        .execute()
    )

    supabase.table("trainers").update({
        "wins": (winner_data.data["wins"] or 0) + 1
    }).eq(
        "username", winner
    ).execute()

    supabase.table("trainers").update({
        "losses": (loser_data.data["losses"] or 0) + 1
    }).eq(
        "username", loser
    ).execute()

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
    response = (
        supabase.table("trainers")
        .select("username, capture, wins")
        .execute()
    )

    rows = response.data

    rows.sort(
        key=lambda row: (
            row["capture"] or 0,
            row["wins"] or 0
        ),
        reverse=True
    )

    rows = rows[:10]

    if not rows:
        return Response(
            "🏆 Ainda não existem treinadores no ranking!",
            mimetype="text/plain; charset=utf-8"
        )

    ranking = []

    for i, row in enumerate(rows, start=1):
        ranking.append(
            f"{i}º {row['username']} "
            f"— 🎒 {row['capture']} Pokémon "
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
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080
)
