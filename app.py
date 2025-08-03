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
    "standard": [
        # 5-Star Items (Characters and Weapons)
        {"name": "Nova Aethel", "rarity": 5, "type": "Character"},
        {"name": "Starlight Aegis", "rarity": 5, "type": "Weapon"},
        {"name": "Kaelus", "rarity": 5, "type": "Character"},
        {"name": "Voidwalker's Blade", "rarity": 5, "type": "Weapon"},
        # 4-Star Items
        {"name": "Cyrus", "rarity": 4, "type": "Character"},
        {"name": "Radiant Staff", "rarity": 4, "type": "Weapon"},
        {"name": "Lyra", "rarity": 4, "type": "Character"},
        {"name": "Shadowstrike Bow", "rarity": 4, "type": "Weapon"},
        # 3-Star Items
        {"name": "Common Sword", "rarity": 3, "type": "Weapon"},
        {"name": "Novice's Robe", "rarity": 3, "type": "Armor"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon"},
    ]
}

# Define Gacha probabilities and pity system
GACHA_RATES = {
    "standard": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943},
    }
}

# In-memory database for user data (for this example)
# In a real application, this would be a persistent database like Firestore or PostgreSQL
user_data = {}

# --- UTILITY FUNCTIONS ---

def show_message(text):
    """Helper to display messages to the user (frontend will handle this)"""
    return jsonify({"status": "error", "message": text})

def validate_telegram_init_data(init_data):
    """
    Validates the Telegram Web App's init data.
    NOTE: For a real application, you would need to get your bot's token.
    For this example, we will skip the cryptographic validation and just parse the data.
    """
    try:
        data_dict = {}
        for item in init_data.split('&'):
            key, value = item.split('=', 1)
            data_dict[key] = unquote(value)

        # Assuming 'user' is always in the data for this example
        user_info = json.loads(data_dict['user'])
        return user_info['id'], data_dict
    except (KeyError, json.JSONDecodeError):
        # In a real app, this would be a validation failure
        return None, None

def get_or_create_user(user_id):
    """
    Retrieves a user's data or creates a new user if one doesn't exist.
    """
    if user_id not in user_data:
        # Initialize a new user with starting currency and pity counters
        user_data[user_id] = {
            "star_night_crystals": 1000,
            "lumen_orbs": 5,
            "halo_orbs": 0,
            "auric_crescents": 0,
            "pity_counters": {
                "standard": {"4_star": 0, "5_star": 0},
                "limited": {"4_star": 0, "5_star": 0},
            },
            "inventory": []
        }
    return user_data[user_id]

def get_pull_result(banner_type, pity_4, pity_5):
    """
    Calculates the outcome of a single gacha pull based on probabilities and pity.
    """
    # Use a copy of the Gacha pool to prevent modification
    pool = list(GACHA_POOL[banner_type])

    # Check for hard pity first
    if pity_5 >= GACHA_RATES[banner_type][5]["hard_pity"] - 1:
        # Guaranteed 5-star
        return random.choice([item for item in pool if item["rarity"] == 5])
    if pity_4 >= GACHA_RATES[banner_type][4]["hard_pity"] - 1:
        # Guaranteed 4-star
        return random.choice([item for item in pool if item["rarity"] >= 4])

    # Soft pity check for 5-star
    roll_rate_5 = GACHA_RATES[banner_type][5]["base_rate"]
    if pity_5 >= GACHA_RATES[banner_type][5]["pity_start"]:
        # Increase probability linearly after soft pity starts
        soft_pity_pulls = pity_5 - GACHA_RATES[banner_type][5]["pity_start"] + 1
        roll_rate_5 += 0.05 * soft_pity_pulls

    # Generate a random number to determine the rarity
    roll = random.random()

    # Determine the rarity based on rates
    if roll < roll_rate_5:
        # 5-Star pull
        return random.choice([item for item in pool if item["rarity"] == 5])
    elif roll < (GACHA_RATES[banner_type][4]["base_rate"] + roll_rate_5):
        # 4-Star pull
        return random.choice([item for item in pool if item["rarity"] == 4])
    else:
        # 3-Star pull (or whatever is left)
        return random.choice([item for item in pool if item["rarity"] == 3])

# --- FLASK ROUTES ---

@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    """
    API endpoint to fetch a user's current currency and pity status.
    Requires 'X-Telegram-Init-Data' header for authentication.
    """
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return show_message("Missing Telegram init data.")

    user_id, _ = validate_telegram_init_data(init_data)
    if not user_id:
        return show_message("Invalid Telegram init data.")

    user = get_or_create_user(user_id)

    return jsonify({
        "status": "success",
        "star_night_crystals": user["star_night_crystals"],
        "lumen_orbs": user["lumen_orbs"],
        "halo_orbs": user["halo_orbs"],
        "auric_crescents": user["auric_crescents"],
        "pity_counters": user["pity_counters"]
    })

@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    """
    API endpoint to perform a gacha pull.
    Requires 'X-Telegram-Init-Data' header and a JSON body.
    """
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        return show_message("Missing Telegram init data.")
    
    user_id, _ = validate_telegram_init_data(init_data)
    if not user_id:
        return show_message("Invalid Telegram init data.")

    data = request.get_json()
    pull_type = data.get('pull_type')
    banner_type = data.get('banner_type')

    if banner_type not in GACHA_POOL:
        return show_message(f"Invalid banner type: {banner_type}.")

    user = get_or_create_user(user_id)

    cost_orb = 10 if pull_type == 'multi' else 1
    cost_snc = 595 if pull_type == 'multi' else 70
    num_pulls = 10 if pull_type == 'multi' else 1
    orb_type = "lumen_orbs" if banner_type == "standard" else "halo_orbs"

    # Check for limited banner availability
    if banner_type == "limited":
        return show_message("The Limited Banner is currently unavailable.")

    # Check if user has enough orbs
    if user[orb_type] >= cost_orb:
        user[orb_type] -= cost_orb
        pulls_remaining = num_pulls
        currency_used = orb_type
    # Check if user has enough SNC to convert
    elif user["star_night_crystals"] >= cost_snc:
        user["star_night_crystals"] -= cost_snc
        pulls_remaining = num_pulls
        currency_used = "star_night_crystals"
    else:
        return show_message("Insufficient currency for this pull.")

    pulled_items = []
    pity_4 = user["pity_counters"][banner_type]["4_star"]
    pity_5 = user["pity_counters"][banner_type]["5_star"]

    for _ in range(num_pulls):
        # Increment pity counters before the pull
        pity_4 += 1
        pity_5 += 1

        result = get_pull_result(banner_type, pity_4, pity_5)
        pulled_items.append(result)
        user["inventory"].append(result)

        # Reset pity counters if a high-rarity item is pulled
        if result["rarity"] >= 4:
            pity_4 = 0
        if result["rarity"] == 5:
            pity_5 = 0

    # Save the updated pity counters back to the user data
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
    """
    API endpoint to handle currency exchanges in the shop.
    Requires 'X-Telegram-Init-Data' header and a JSON body.
    """
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
def serve_html():
    """Serves the main HTML file."""
    # This assumes the HTML is saved in a file named `game.html`
    return render_template('game.html')

if __name__ == '__main__':
    # For local development, you might want to run with debug=True
    # For production, this should be run by a proper WSGI server like Gunicorn
    app.run(host='0.0.0.0', port=5000, debug=True)

