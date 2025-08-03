import os
import json
import requests
import hmac
import hashlib
import random # Corrected: Added the missing import for the random module
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

# Gacha rates (cumulative)
RATES = {
    5: 0.02, # 2% for a 5-star
    4: 0.10, # 10% for a 4-star (8% after 5-star rate)
    3: 1.00  # 100% for a 3-star (90% after 4-star and 5-star)
}

# Gacha costs
COSTS = {
    'single': 100,
    'multi': 900
}

# Gacha pity counters
PITY_4_STAR = 10
PITY_5_STAR = 90

# Function to get or create a user document
def get_user_data(user_id):
    """Retrieves user data from Firestore or creates a new user if one doesn't exist."""
    user_doc = users_ref.document(user_id).get()
    if user_doc.exists:
        return user_doc.to_dict()
    else:
        # Create a new user with default values
        new_user_data = {
            'star_night_crystals': 2000, # Starting crystals for new users
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
    """
    Corrected: This API endpoint was missing from a previous version,
    causing the 404 error on the client side.
    """
    init_data = request.headers.get('X-Telegram-Init-Data')
    user_id = get_user_from_telegram_init_data(init_data)

    if not user_id:
        return jsonify({"status": "error", "message": "Invalid or missing Telegram init data"}), 401

    try:
        user_data = get_user_data(user_id)
        return jsonify({"status": "success", "star_night_crystals": user_data['star_night_crystals']})
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return jsonify({"status": "error", "message": "Failed to fetch user data"}), 500

# API Route for gacha pull
@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    """
    Corrected: This API endpoint was also missing from a previous version.
    """
    init_data = request.headers.get('X-Telegram-Init-Data')
    user_id = get_user_from_telegram_init_data(init_data)

    if not user_id:
        return jsonify({"status": "error", "message": "Invalid or missing Telegram init data"}), 401
    
    try:
        user_data = get_user_data(user_id)
        pull_type = request.json.get('pull_type', 'single')
        cost = COSTS.get(pull_type, 100)
        num_pulls = 1 if pull_type == 'single' else 10

        if user_data['star_night_crystals'] < cost:
            return jsonify({"status": "error", "message": "Not enough Star-Night Crystals"}), 400

        user_data['star_night_crystals'] -= cost
        pulled_characters = []
        new_owned_characters = list(user_data['owned_characters'])

        for _ in range(num_pulls):
            # Check pity counters first
            if user_data['gacha_pity_5_star'] >= PITY_5_STAR - 1:
                pulled_char = CHARACTERS["Nova"] # Pity character
                pulled_char_name = "Nova"
                user_data['gacha_pity_5_star'] = 0
                user_data['gacha_pity_4_star'] += 1
            elif user_data['gacha_pity_4_star'] >= PITY_4_STAR - 1:
                pulled_char = CHARACTERS["Vex"] # Pity character
                pulled_char_name = "Vex"
                user_data['gacha_pity_4_star'] = 0
                user_data['gacha_pity_5_star'] += 1
            else:
                # Random pull
                roll = random.random()
                if roll < RATES[5]:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 5])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    user_data['gacha_pity_5_star'] = 0
                    user_data['gacha_pity_4_star'] += 1
                elif roll < RATES[4]:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 4])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    user_data['gacha_pity_4_star'] = 0
                    user_data['gacha_pity_5_star'] += 1
                else:
                    pulled_char = random.choice([c for c in CHARACTERS.values() if c['rarity'] == 3])
                    pulled_char_name = [name for name, char in CHARACTERS.items() if char == pulled_char][0]
                    user_data['gacha_pity_5_star'] += 1
                    user_data['gacha_pity_4_star'] += 1
            
            pulled_characters.append({"name": pulled_char_name, "rarity": pulled_char['rarity']})
            new_owned_characters.append(pulled_char_name)

        # Update Firestore
        users_ref.document(user_id).update({
            'star_night_crystals': user_data['star_night_crystals'],
            'owned_characters': new_owned_characters,
            'gacha_pity_4_star': user_data['gacha_pity_4_star'],
            'gacha_pity_5_star': user_data['gacha_pity_5_star']
        })

        return jsonify({
            "status": "success",
            "pulled_characters": pulled_characters,
            "remaining_crystals": user_data['star_night_crystals']
        })
    except Exception as e:
        print(f"Error during gacha pull: {e}")
        return jsonify({"status": "error", "message": "An unexpected error occurred"}), 500

if __name__ == '__main__':
    # This is for local development only
    # In production on Render, Gunicorn will run the app
    # app.run(host='0.0.0.0', port=5000)
    pass
