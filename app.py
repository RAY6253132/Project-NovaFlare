import os
import json
import requests
import hmac
import hashlib
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from firebase_admin import credentials, firestore, initialize_app

# Set up Firebase credentials
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if FIREBASE_SERVICE_ACCOUNT_JSON:
    cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
else:
    # This path is for local development only and assumes a file exists.
    # It should not be used in production.
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
    except FileNotFoundError:
        print("Error: Firebase service account key not found.")
        exit(1)

initialize_app(cred)
db = firestore.client()
users_ref = db.collection('users')

app = Flask(__name__)

# Gacha Character Database
CHARACTERS = {
    "Nova": {"rarity": 5},
    "Starlight": {"rarity": 5},
    "Vex": {"rarity": 4},
    "Cinder": {"rarity": 4},
    "Breeze": {"rarity": 3},
    "Echo": {"rarity": 3},
    "Bolt": {"rarity": 3}
}

# Base gacha rates (non-cumulative)
BASE_RATES = {
    5: 0.02,  # 2% for a 5-star
    4: 0.08,  # 8% for a 4-star
    3: 0.90   # 90% for a 3-star
}

# Gacha rates (cumulative) for rolling
# This makes the gacha logic easier to implement
CUMULATIVE_RATES = {
    5: BASE_RATES[5],
    4: BASE_RATES[5] + BASE_RATES[4],
    3: BASE_RATES[5] + BASE_RATES[4] + BASE_RATES[3]
}

# Gacha pity counters
PITY_4_STAR = 10
PITY_5_STAR = 90

# Currency conversion rates
ORB_PULL_COST = 1
ORB_MULTI_PULL_COST = 10
LUMEN_ORB_SNC_COST = 70
LUMEN_ORB_SNC_DISCOUNT_MULTIPLIER = 0.85
HALO_ORB_SNC_COST = 100
HALO_ORB_SNC_DISCOUNT_MULTIPLIER = 0.90
AC_TO_ORB_COST = 20

# Auric Crescent rewards
AC_REWARDS = {
    4: 20,
    5: 40
}

# Function to get or create a user document
def get_user_data(user_id):
    """Retrieves user data from Firestore or creates a new user if one doesn't exist."""
    user_doc = users_ref.document(user_id).get()
    if user_doc.exists:
        return user_doc.to_dict()
    else:
        # Create a new user with default values
        new_user_data = {
            'star_night_crystals': 2000,
            'lumen_orbs': 0,
            'halo_orbs': 0,
            'auric_crescents': 0,
            'owned_characters': [],
            'gacha_pity_4_star': 0,
            'gacha_pity_5_star': 0
        }
        users_ref.document(user_id).set(new_user_data)
        return new_user_data

def get_user_from_telegram_init_data(init_data):
    """
    Validates initData and extracts user information.
    Note: In a real-world app, you would also use the bot token to validate the hash.
    For this example, we'll assume the hash is valid as long as init_data is present.
    """
    # Parse the init_data string
    params = dict(item.split('=', 1) for item in init_data.split('&'))
    
    # Check if user data exists
    if 'user' not in params:
        return None

    # Extract user ID from the user JSON string
    user_data = json.loads(requests.utils.unquote(params['user']))
    user_id = str(user_data['id'])
    return user_id


# --- New Routes for Homepage and Game ---
@app.route('/')
def home():
    """Renders the main homepage (the new index.html)."""
    return render_template('index.html')

@app.route('/game')
def game_page():
    """Renders the gacha game page (the renamed index.html)."""
    return render_template('game.html')
# --- End of New Routes ---

# API Route to get user data
@app.route('/get_user_data', methods=['GET'])
def get_user_data_api():
    init_data = request.headers.get('X-Telegram-Init-Data')
    user_id = get_user_from_telegram_init_data(init_data)

    if not user_id:
        return jsonify({"status": "error", "message": "Invalid or missing Telegram init data"}), 401

    try:
        user_data = get_user_data(user_id)
        return jsonify({
            "status": "success",
            "star_night_crystals": user_data['star_night_crystals'],
            "lumen_orbs": user_data['lumen_orbs'],
            "halo_orbs": user_data['halo_orbs'],
            "auric_crescents": user_data['auric_crescents'],
            "pity_counters": {
                "standard": {"4_star": user_data['gacha_pity_4_star'], "5_star": user_data['gacha_pity_5_star']},
                "limited": {"4_star": user_data['gacha_pity_4_star'], "5_star": user_data['gacha_pity_5_star']}
            }
        })
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return jsonify({"status": "error", "message": "Failed to fetch user data"}), 500

# API Route for gacha pull
@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    init_data = request.headers.get('X-Telegram-Init-Data')
    user_id = get_user_from_telegram_init_data(init_data)

    if not user_id:
        return jsonify({"status": "error", "message": "Invalid or missing Telegram init data"}), 401
    
    try:
        user_data = get_user_data(user_id)
        pull_type = request.json.get('pull_type') # 'single' or 'multi'
        banner_type = request.json.get('banner_type') # 'standard' or 'limited'
        
        num_pulls = 1 if pull_type == 'single' else 10

        # Determine currency and costs
        if banner_type == 'standard':
            orb_type = 'lumen_orbs'
            orb_cost = ORB_PULL_COST if pull_type == 'single' else ORB_MULTI_PULL_COST
            snc_cost = LUMEN_ORB_SNC_COST if pull_type == 'single' else int(LUMEN_ORB_SNC_COST * 10 * LUMEN_ORB_SNC_DISCOUNT_MULTIPLIER)
            currency_name = "Lumen Orb"
        elif banner_type == 'limited':
            orb_type = 'halo_orbs'
            orb_cost = ORB_PULL_COST if pull_type == 'single' else ORB_MULTI_PULL_COST
            snc_cost = HALO_ORB_SNC_COST if pull_type == 'single' else int(HALO_ORB_SNC_COST * 10 * HALO_ORB_SNC_DISCOUNT_MULTIPLIER)
            currency_name = "Halo Orb"
        else:
            return jsonify({"status": "error", "message": "Invalid banner type"}), 400

        # Check for orbs, and if not enough, check for SNC to convert
        if user_data[orb_type] < orb_cost:
            if user_data['star_night_crystals'] < snc_cost:
                return jsonify({"status": "error", "message": f"Not enough {currency_name}s or Star-Night Crystals."}), 400
            
            # Auto-convert SNC to orbs and perform pull
            user_data['star_night_crystals'] -= snc_cost
        else:
            # Use existing orbs
            user_data[orb_type] -= orb_cost

        pulled_characters = []
        new_owned_characters = list(user_data['owned_characters'])

        for _ in range(num_pulls):
            # Check pity counters first
            if user_data['gacha_pity_5_star'] >= PITY_5_STAR - 1:
                pulled_char = CHARACTERS["Nova"] # Pity character
                pulled_char_name = "Nova"
                pulled_rarity = 5
                user_data['gacha_pity_5_star'] = 0
                user_data['gacha_pity_4_star'] += 1
            elif user_data['gacha_pity_4_star'] >= PITY_4_STAR - 1:
                pulled_char = CHARACTERS["Vex"] # Pity character
                pulled_char_name = "Vex"
                pulled_rarity = 4
                user_data['gacha_pity_4_star'] = 0
                user_data['gacha_pity_5_star'] += 1
            else:
                # Random pull
                roll = random.random()
                if roll < CUMULATIVE_RATES[5]:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 5])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    pulled_rarity = 5
                    user_data['gacha_pity_5_star'] = 0
                    user_data['gacha_pity_4_star'] += 1
                elif roll < CUMULATIVE_RATES[4]:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 4])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    pulled_rarity = 4
                    user_data['gacha_pity_4_star'] = 0
                    user_data['gacha_pity_5_star'] += 1
                else:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 3])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    pulled_rarity = 3
                    user_data['gacha_pity_5_star'] += 1
                    user_data['gacha_pity_4_star'] += 1
            
            pulled_characters.append({"name": pulled_char_name, "rarity": pulled_rarity})
            new_owned_characters.append(pulled_char_name)

            # Award Auric Crescents
            if pulled_rarity in AC_REWARDS:
                user_data['auric_crescents'] += AC_REWARDS[pulled_rarity]

        # Update Firestore
        users_ref.document(user_id).update({
            'star_night_crystals': user_data['star_night_crystals'],
            'lumen_orbs': user_data['lumen_orbs'],
            'halo_orbs': user_data['halo_orbs'],
            'auric_crescents': user_data['auric_crescents'],
            'owned_characters': new_owned_characters,
            'gacha_pity_4_star': user_data['gacha_pity_4_star'],
            'gacha_pity_5_star': user_data['gacha_pity_5_star']
        })

        return jsonify({
            "status": "success",
            "pulled_items": pulled_characters,
            "remaining_crystals": user_data['star_night_crystals'],
            "remaining_lumen_orbs": user_data['lumen_orbs'],
            "remaining_halo_orbs": user_data['halo_orbs'],
            "remaining_auric_crescents": user_data['auric_crescents'],
            "pity_4_star": user_data['gacha_pity_4_star'],
            "pity_5_star": user_data['gacha_pity_5_star']
        })
    except Exception as e:
        print(f"Error during gacha pull: {e}")
        return jsonify({"status": "error", "message": "An unexpected error occurred"}), 500

@app.route('/exchange_shop', methods=['POST'])
def exchange_shop():
    """
    Handles currency exchange in the shop.
    """
    init_data = request.headers.get('X-Telegram-Init-Data')
    user_id = get_user_from_telegram_init_data(init_data)
    if not user_id:
        return jsonify({"status": "error", "message": "Invalid or missing Telegram init data"}), 401

    try:
        user_data = get_user_data(user_id)
        exchange_type = request.json.get('exchange_type') # e.g., 'buy_lumen_1', 'buy_lumen_10', 'exchange_lumen'
        
        # Define costs and updates
        updates = {}
        if exchange_type == 'buy_lumen_1':
            cost = LUMEN_ORB_SNC_COST
            if user_data['star_night_crystals'] < cost:
                return jsonify({"status": "error", "message": "Not enough SNC"}), 400
            updates = {'star_night_crystals': user_data['star_night_crystals'] - cost, 'lumen_orbs': user_data['lumen_orbs'] + 1}
        elif exchange_type == 'buy_lumen_10':
            cost = int(LUMEN_ORB_SNC_COST * 10 * LUMEN_ORB_SNC_DISCOUNT_MULTIPLIER)
            if user_data['star_night_crystals'] < cost:
                return jsonify({"status": "error", "message": "Not enough SNC"}), 400
            updates = {'star_night_crystals': user_data['star_night_crystals'] - cost, 'lumen_orbs': user_data['lumen_orbs'] + 10}
        elif exchange_type == 'buy_halo_1':
            cost = HALO_ORB_SNC_COST
            if user_data['star_night_crystals'] < cost:
                return jsonify({"status": "error", "message": "Not enough SNC"}), 400
            updates = {'star_night_crystals': user_data['star_night_crystals'] - cost, 'halo_orbs': user_data['halo_orbs'] + 1}
        elif exchange_type == 'buy_halo_10':
            cost = int(HALO_ORB_SNC_COST * 10 * HALO_ORB_SNC_DISCOUNT_MULTIPLIER)
            if user_data['star_night_crystals'] < cost:
                return jsonify({"status": "error", "message": "Not enough SNC"}), 400
            updates = {'star_night_crystals': user_data['star_night_crystals'] - cost, 'halo_orbs': user_data['halo_orbs'] + 10}
        elif exchange_type == 'exchange_lumen':
            cost = AC_TO_ORB_COST
            if user_data['auric_crescents'] < cost:
                return jsonify({"status": "error", "message": "Not enough Auric Crescents"}), 400
            updates = {'auric_crescents': user_data['auric_crescents'] - cost, 'lumen_orbs': user_data['lumen_orbs'] + 1}
        elif exchange_type == 'exchange_halo':
            cost = AC_TO_ORB_COST
            if user_data['auric_crescents'] < cost:
                return jsonify({"status": "error", "message": "Not enough Auric Crescents"}), 400
            updates = {'auric_crescents': user_data['auric_crescents'] - cost, 'halo_orbs': user_data['halo_orbs'] + 1}
        else:
            return jsonify({"status": "error", "message": "Invalid exchange type"}), 400
        
        # Update Firestore
        users_ref.document(user_id).update(updates)
        
        return jsonify({
            "status": "success",
            "star_night_crystals": updates.get('star_night_crystals', user_data['star_night_crystals']),
            "lumen_orbs": updates.get('lumen_orbs', user_data['lumen_orbs']),
            "halo_orbs": updates.get('halo_orbs', user_data['halo_orbs']),
            "auric_crescents": updates.get('auric_crescents', user_data['auric_crescents'])
        })

    except Exception as e:
        print(f"Error during shop exchange: {e}")
        return jsonify({"status": "error", "message": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    # This is for local development only
    # In production on Render, Gunicorn will run the app
    # app.run(host='0.0.0.0', port=5000)
    pass
