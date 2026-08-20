from flask import Flask, Response
import random
import requests

app = Flask(__name__)

POKEAPI = "https://pokeapi.co/api/v2/pokemon-species?limit=1000"
_cache = None

# Pesos de encontro: comum 55%, incomum 25%, raro 13%, lendário 6%, mítico 1%.
RARITY_WEIGHTS = [
    ("comum", 55),
    ("incomum", 25),
    ("raro", 13),
    ("lendario", 6),
    ("mitico", 1),
]

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

def load_species():
    global _cache
    if _cache is not None:
        return _cache

    data = requests.get(POKEAPI, timeout=15).json()
    species = data["results"]

    # A API retorna espécies. Usamos os dados de cada espécie para separar
    # lendários e míticos; o restante é distribuído por raridade.
    enriched = []
    for item in species:
        try:
            s = requests.get(item["url"], timeout=10).json()
            name = s["name"].replace("-", " ")
            if s.get("is_mythical"):
                rarity = "mitico"
            elif s.get("is_legendary"):
                rarity = "lendario"
            else:
                # Distribuição determinística simples para o restante:
                # espécies iniciais/evoluções não lendárias ficam entre
                # comum, incomum e raro.
                n = s["id"]
                if n % 10 < 6:
                    rarity = "comum"
                elif n % 10 < 9:
                    rarity = "incomum"
                else:
                    rarity = "raro"
            enriched.append((name, rarity))
        except Exception:
            pass

    _cache = enriched
    return _cache

def pick_rarity():
    names = [x[0] for x in RARITY_WEIGHTS]
    weights = [x[1] for x in RARITY_WEIGHTS]
    return random.choices(names, weights=weights, k=1)[0]

def pick_pokemon(rarity):
    all_species = load_species()
    pool = [name for name, r in all_species if r == rarity]
    if not pool:
        pool = [name for name, r in all_species if r == "comum"]
    return random.choice(pool)

def make_result(user):
    rarity = pick_rarity()
    pokemon = pick_pokemon(rarity)
    chance = CAPTURE_CHANCES[rarity]
    roll = random.random()

    # Pequena chance de evento especial dentro de cada encontro.
    critical = random.random() < 0.05
    counter = random.random() < 0.22

    if critical:
        outcome = f"💥 CAPTURA CRÍTICA! {user} capturou {pokemon}!"
    elif roll < chance:
        if rarity == "mitico":
            outcome = f"✨ INACREDITÁVEL! {user} capturou o MÍTICO {pokemon}!"
        elif rarity == "lendario":
            outcome = f"🌟 LENDA CAPTURADA! {user} conseguiu capturar o LENDÁRIO {pokemon}!"
        elif rarity == "raro":
            outcome = f"🎉 Boa! {user} capturou o RARO {pokemon}!"
        else:
            outcome = f"🎉 {user} capturou {pokemon}!"
    elif counter:
        outcome = f"⚡ {pokemon} revidou! {user} foi atingido e ficou desmaiado!"
    else:
        outcome = f"😱 {pokemon} escapou da Pokébola no último instante!"

    return f"{user} encontrou {pokemon}! {RARITY_LABEL[rarity]} — {outcome}"

@app.get("/pokemon")
def pokemon():
    user = "O treinador"
    return Response(make_result(user), mimetype="text/plain; charset=utf-8")

@app.get("/pokemon/<user>")
def pokemon_user(user):
    # O StreamElements deve enviar um nome já escapado na URL.
    return Response(make_result(user), mimetype="text/plain; charset=utf-8")

@app.get("/")
def home():
    return "Pokemon chatbot API online."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
