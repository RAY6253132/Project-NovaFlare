import json
import random
import hmac
import hashlib
import time
from urllib.parse import unquote
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# --- GACHA CONFIGURATION AND ITEM POOL ---

# Define the Signal/Character Pool
GACHA_POOL = {
    # Standard banner pool
    "standard_character": [
        {"name": "Nova Aethel", "rarity": 5, "type": "Character"},
        {"name": "Kaelus", "rarity": 5, "type": "Character"},
        {"name": "Cyrus", "rarity": 4, "type": "Character"},
        {"name": "Lyra", "rarity": 4, "type": "Character"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon"},
        {"name": "Novice's Robe", "rarity": 3, "type": "Armor"},
    ],
    "standard_weapon": [
        {"name": "Starlight Aegis", "rarity": 5, "type": "Weapon"},
        {"name": "Voidwalker's Blade", "rarity": 5, "type": "Weapon"},
        {"name": "Radiant Staff", "rarity": 4, "type": "Weapon"},
        {"name": "Shadowstrike Bow", "rarity": 4, "type": "Weapon"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon"},
    ],
    # Limited banner pools
    "limited_character_1": [
        {"name": "Limited Character A", "rarity": 5, "type": "Character", "is_limited": True},
        {"name": "Limited Character B", "rarity": 4, "type": "Character", "is_limited": True},
        {"name": "Nova Aethel", "rarity": 5, "type": "Character"},
        {"name": "Cyrus", "rarity": 4, "type": "Character"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon"},
    ],
    "limited_character_2": [
        {"name": "Limited Character C", "rarity": 5, "type": "Character", "is_limited": True},
        {"name": "Limited Character D", "rarity": 4, "type": "Character", "is_limited": True},
        {"name": "Kaelus", "rarity": 5, "type": "Character"},
        {"name": "Lyra", "rarity": 4, "type": "Character"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon"},
    ],
    "limited_weapon_1": [
        {"name": "Limited Weapon A", "rarity": 5, "type": "Weapon", "is_limited": True},
        {"name": "Limited Weapon B", "rarity": 4, "type": "Weapon", "is_limited": True},
        {"name": "Starlight Aegis", "rarity": 5, "type": "Weapon"},
        {"name": "Radiant Staff", "rarity": 4, "type": "Weapon"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon"},
    ],
    "limited_weapon_2": [
        {"name": "Limited Weapon C", "rarity": 5, "type": "Weapon", "is_limited": True},
        {"name": "Limited Weapon D", "rarity": 4, "type": "Weapon", "is_limited": True},
        {"name": "Voidwalker's Blade", "rarity": 5, "type": "Weapon"},
        {"name": "Shadowstrike Bow", "rarity": 4, "type": "Weapon"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon"},
    ],
}

# Define Gacha probabilities and pity system
GACHA_RATES = {
    # Standard banner rates
    "standard_character": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
    "standard_weapon": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
    # Limited banner rates (example, can be customized)
    "limited_character_1": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
    "limited_character_2": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
    "limited_weapon_1": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
    "limited_weapon_2": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    },
}

# In-memory database for user data (for this example)
user_data = {}

# Your Telegram Bot Token (GET THIS FROM BOTFATHER)
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE" 

# --- UTILITY FUNCTIONS ---

def show_message(text):
    return jsonify({"status": "error", "message": text})

def validate_telegram_init_data(init_data):
    try:
        data_dict = {}
        for item in init_data.split('&'):
            key, value = item.split('=', 1)
            data_dict[key] = unquote(value)

        user_info = json.loads(data_dict['user'])
        return user_info['id'], data_dict
    except (KeyError, json.JSONDecodeError, AttributeError):
        return None, None

def get_or_create_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "star_night_crystals": 1000,
            "lumen_orbs": 5,
            "halo_orbs": 0,
            "auric_crescents": 0,
            "pity_counters": {
                "standard_character": {"4_star": 0, "5_star": 0},
                "standard_weapon": {"4_star": 0, "5_star": 0},
                "limited_character_1": {"4_star": 0, "5_star": 0},
                "limited_character_2": {"4_star": 0, "5_star": 0},
                "limited_weapon_1": {"4_star": 0, "5_star": 0},
                "limited_weapon_2": {"4_star": 0, "5_star": 0},
            },
            "inventory": []
        }
    return user_data[user_id]

def get_pull_result(banner_type, pity_4, pity_5):
    pool = list(GACHA_POOL.get(banner_type, []))

    if not pool:
        return {"name": "Error", "rarity": 0, "type": "Error"} # Should not happen with validation

    if pity_5 >= GACHA_RATES[banner_type][5]["hard_pity"] - 1:
        return random.choice([item for item in pool if item["rarity"] == 5])
    if pity_4 >= GACHA_RATES[banner_type][4]["hard_pity"] - 1:
        return random.choice([item for item in pool if item["rarity"] >= 4])

    roll_rate_5 = GACHA_RATES[banner_type][5]["base_rate"]
    if pity_5 >= GACHA_RATES[banner_type][5]["pity_start"]:
        soft_pity_pulls = pity_5 - GACHA_RATES[banner_type][5]["pity_start"] + 1
        roll_rate_5 += 0.05 * soft_pity_pulls

    roll = random.random()

    if roll < roll_rate_5:
        return random.choice([item for item in pool if item["rarity"] == 5])
    elif roll < (GACHA_RATES[banner_type][4]["base_rate"] + roll_rate_5):
        return random.choice([item for item in pool if item["rarity"] == 4])
    else:
        return random.choice([item for item in pool if item["rarity"] == 3])

# --- FLASK ROUTES ---

@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return show_message("Missing Telegram init data.")

    user_id, _ = validate_telegram_init_data(init_data)
    if not user_id:
        return show_message("Invalid Telegram init data.")

    user = get_or_create_user(user_id)

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "star_night_crystals": user["star_night_crystals"],
        "lumen_orbs": user["lumen_orbs"],
        "halo_orbs": user["halo_orbs"],
        "auric_crescents": user["auric_crescents"],
        "pity_counters": user["pity_counters"]
    })

@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return show_message("Missing Telegram init data.")
    
    user_id, _ = validate_telegram_init_data(init_data)
    if not user_id:
        return show_message("Invalid Telegram init data.")

    data = request.get_json()
    pull_type = data.get('pull_type')
    banner_type = data.get('banner_type')

    # The issue was here: The banner type was not in your GACHA_POOL
    if banner_type not in GACHA_POOL:
        return show_message(f"Invalid banner type: {banner_type}.")

    user = get_or_create_user(user_id)

    cost_orb = 10 if pull_type == 'multi' else 1
    cost_snc = 595 if pull_type == 'multi' else 70
    num_pulls = 10 if pull_type == 'multi' else 1
    
    # Updated logic to select the correct currency based on banner type
    if 'standard' in banner_type:
        orb_type = "lumen_orbs"
    elif 'limited' in banner_type:
        orb_type = "halo_orbs"
    else:
        return show_message("Invalid banner type for currency check.")

    if user[orb_type] >= cost_orb:
        user[orb_type] -= cost_orb
        currency_used = orb_type
    elif user["star_night_crystals"] >= cost_snc:
        user["star_night_crystals"] -= cost_snc
        currency_used = "star_night_crystals"
    else:
        return show_message("Insufficient currency for this pull.")

    pulled_items = []
    pity_4 = user["pity_counters"][banner_type]["4_star"]
    pity_5 = user["pity_counters"][banner_type]["5_star"]

    for _ in range(num_pulls):
        pity_4 += 1
        pity_5 += 1

        result = get_pull_result(banner_type, pity_4, pity_5)
        pulled_items.append(result)
        user["inventory"].append(result)

        if result["rarity"] >= 4:
            pity_4 = 0
        if result["rarity"] == 5:
            pity_5 = 0

    user["pity_counters"][banner_type]["4_star"] = pity_4
    user["pity_counters"][banner_type]["5_star"] = pity_5

    return jsonify({
        "status": "success",
        "pulled_items": pulled_items,
        "remaining_crystals": user["star_night_crystals"],
        "remaining_lumen_orbs": user["lumen_orbs"],
        "remaining_halo_orbs": user["halo_orbs"],
        "remaining_auric_crescents": user["auric_crescents"],
        "pity_4_star": pity_4,
        "pity_5_star": pity_5
    })

@app.route('/exchange_shop', methods=['POST'])
def exchange_shop():
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return show_message("Missing Telegram init data.")
    
    user_id, _ = validate_telegram_init_data(init_data)
    if not user_id:
        return show_message("Invalid Telegram init data.")

    data = request.get_json()
    exchange_type = data.get('exchange_type')
    user = get_or_create_user(user_id)

    if exchange_type == 'buy_lumen_1':
        if user["star_night_crystals"] >= 70:
            user["star_night_crystals"] -= 70
            user["lumen_orbs"] += 1
        else:
            return show_message("Not enough SNC.")
    elif exchange_type == 'buy_lumen_10':
        if user["star_night_crystals"] >= 595:
            user["star_night_crystals"] -= 595
            user["lumen_orbs"] += 10
        else:
            return show_message("Not enough SNC.")
    elif exchange_type == 'buy_halo_1':
        if user["star_night_crystals"] >= 100:
            user["star_night_crystals"] -= 100
            user["halo_orbs"] += 1
        else:
            return show_message("Not enough SNC.")
    elif exchange_type == 'buy_halo_10':
        if user["star_night_crystals"] >= 900:
            user["star_night_crystals"] -= 900
            user["halo_orbs"] += 10
        else:
            return show_message("Not enough SNC.")
    elif exchange_type == 'exchange_lumen':
        if user["auric_crescents"] >= 20:
            user["auric_crescents"] -= 20
            user["lumen_orbs"] += 1
        else:
            return show_message("Not enough Auric Crescents.")
    elif exchange_type == 'exchange_halo':
        if user["auric_crescents"] >= 20:
            user["auric_crescents"] -= 20
            user["halo_orbs"] += 1
        else:
            return show_message("Not enough Auric Crescents.")
    else:
        return show_message("Invalid exchange type.")

    return jsonify({
        "status": "success",
        "star_night_crystals": user["star_night_crystals"],
        "lumen_orbs": user["lumen_orbs"],
        "halo_orbs": user["halo_orbs"],
        "auric_crescents": user["auric_crescents"]
    })

@app.route('/')
def serve_index_html():
    return render_template('index.html')

@app.route('/game')
def serve_game_html():
    return render_template('game.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)