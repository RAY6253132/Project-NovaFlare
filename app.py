import os
import random # We'll need this for gacha pulls!
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS # Add this import
from firebase_admin import credentials, firestore, initialize_app
import json # Make sure this is imported

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Firebase Initialization ---
# IMPORTANT: The local path is only a fallback for local development.
# On Render, it will use the FIREBASE_SERVICE_ACCOUNT_JSON environment variable.

# Try to load credentials from environment variable first (for Render deployment)
if os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"):
    try:
        cred_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        cred_json = json.loads(cred_json_str)
        cred = credentials.Certificate(cred_json)
        initialize_app(cred) # Use initialize_app directly, as it's imported
        print("Firebase initialized from environment variable.")
    except Exception as e:
        print(f"Error initializing Firebase from environment variable: {e}")
        # Fallback to local file if env var parsing fails, or for local dev
        FIREBASE_SERVICE_ACCOUNT_KEY_PATH = 'novaflare-8ef00-firebase-adminsdk-fbsvc-3043593dc0.json'
        if os.path.exists(FIREBASE_SERVICE_ACCOUNT_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_KEY_PATH)
            initialize_app(cred) # Use initialize_app directly
            print("Firebase initialized from local file (fallback due to env var issue).")
        else:
            raise FileNotFoundError(
                f"Service account key not found locally at {FIREBASE_SERVICE_ACCOUNT_KEY_PATH} "
                "and not available as environment variable. "
                "Ensure FIREBASE_SERVICE_ACCOUNT_JSON is set on Render or "
                "the JSON file is present locally for development."
            )
else:
    # Fallback to local file for local development if no env var is set
    FIREBASE_SERVICE_ACCOUNT_KEY_PATH = 'novaflare-8ef00-firebase-adminsdk-fbsvc-3043593dc0.json'
    if os.path.exists(FIREBASE_SERVICE_ACCOUNT_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_KEY_PATH)
        initialize_app(cred) # Use initialize_app directly
        print("Firebase initialized from local file.")
    else:
        raise FileNotFoundError(
            f"Service account key not found locally at {FIREBASE_SERVICE_ACCOUNT_KEY_PATH} "
            "and not available as environment variable. "
            "Ensure FIREBASE_SERVICE_ACCOUNT_JSON is set on Render or "
            "the JSON file is present locally for development."
        )

db = firestore.client()

# --- Placeholder Character Data (for Gacha Pool) ---
# In a real game, this would likely be loaded from Firestore or a config.
# For MVP, we define a small pool of example characters.
CHARACTER_POOL = [
    # 5-Star Characters
    {"id": "c001_elara", "name": "Elara, Cyber Mage", "rarity": 5, "class": "DPS", "element": "Cyber"},
    {"id": "c002_titan", "name": "Titan, Mech Knight", "rarity": 5, "class": "DPS", "element": "Mech"},
    # 4-Star Characters
    {"id": "c003_aura", "name": "Aura, Chrono Healer", "rarity": 4, "class": "Support", "element": "Time"},
    {"id": "c004_glitch", "name": "Glitch, Rogue Hacker", "rarity": 4, "class": "Sub DPS", "element": "Data"},
    {"id": "c005_synthia", "name": "Synthia, Bio-Alchemist", "rarity": 4, "class": "Support", "element": "Bio"},
    # 3-Star Characters
    {"id": "c006_spark", "name": "Spark, Drone Operator", "rarity": 3, "class": "DPS", "element": "Electric"},
    {"id": "c007_rune", "name": "Rune, Street Mystic", "rarity": 3, "class": "Sub DPS", "element": "Arcane"},
    {"id": "c008_volt", "name": "Volt, Cyber Enforcer", "rarity": 3, "class": "DPS", "element": "Electric"},
    {"id": "c009_shroud", "name": "Shroud, Shadow Thief", "rarity": 3, "class": "Sub DPS", "element": "Void"},
    {"id": "c010_core", "name": "Core, Utility Bot", "rarity": 3, "class": "Support", "element": "Mech"},
]

# Separate characters by rarity for easier pulling
FIVE_STAR_CHARS = [c for c in CHARACTER_POOL if c["rarity"] == 5]
FOUR_STAR_CHARS = [c for c in CHARACTER_POOL if c["rarity"] == 4]
THREE_STAR_CHARS = [c for c in CHARACTER_POOL if c["rarity"] == 3]

# --- Gacha Configuration (from Confirmed NovaFlare Game Design Aspects) ---
GACHA_CONFIG = {
    "pull_cost_single": 100,
    "pull_cost_multi": 900,
    "pity_4_star_guarantee": 10,
    "pity_5_star_guarantee": 70,
    "probabilities": {
        5: 1.0,  # 1.0%
        4: 10.0, # 10.0%
        3: 89.0, # 89.0%
    }
}

def perform_single_pull(current_4_star_pity, current_5_star_pity):
    """
    Performs a single gacha pull based on defined probabilities and pity.

    Args:
        current_4_star_pity (int): Number of pulls since last 4-star or higher.
        current_5_star_pity (int): Number of pulls since last 5-star.

    Returns:
        dict: The character dictionary that was pulled.
        int: Updated 4-star pity counter.
        int: Updated 5-star pity counter.
    """
    roll = random.uniform(0, 100) # Generates a float between 0.0 and 100.0

    pulled_rarity = None

    # Check for 5-star pity
    if current_5_star_pity >= GACHA_CONFIG["pity_5_star_guarantee"] - 1: # -1 because it's the Nth pull
        pulled_rarity = 5
    # Check for 4-star pity (only if 5-star pity didn't hit)
    elif current_4_star_pity >= GACHA_CONFIG["pity_4_star_guarantee"] - 1:
        # If 4-star pity hits, it could still be a 5-star based on natural rate
        if roll < GACHA_CONFIG["probabilities"][5]:
            pulled_rarity = 5
        else:
            pulled_rarity = 4
    # Normal probabilities if no pity has been reached
    else:
        if roll < GACHA_CONFIG["probabilities"][5]:
            pulled_rarity = 5
        elif roll < GACHA_CONFIG["probabilities"][5] + GACHA_CONFIG["probabilities"][4]:
            pulled_rarity = 4
        else:
            pulled_rarity = 3

    # Select a random character of the determined rarity
    pulled_character = {}
    if pulled_rarity == 5:
        pulled_character = random.choice(FIVE_STAR_CHARS)
        new_4_star_pity = 0 # Reset 4-star pity on 5-star pull
        new_5_star_pity = 0 # Reset 5-star pity on 5-star pull
    elif pulled_rarity == 4:
        pulled_character = random.choice(FOUR_STAR_CHARS)
        new_4_star_pity = 0 # Reset 4-star pity on 4-star pull
        new_5_star_pity = current_5_star_pity + 1 # Increment 5-star pity
    else: # 3-star
        pulled_character = random.choice(THREE_STAR_CHARS)
        new_4_star_pity = current_4_star_pity + 1 # Increment 4-star pity
        new_5_star_pity = current_5_star_pity + 1 # Increment 5-star pity

    return pulled_character, new_4_star_pity, new_5_star_pity

# --- Basic Home Route (to check if Flask is running) ---
@app.route('/')
def home():
    return render_template('index.html') # This tells Flask to serve your HTML file

# --- Test Firestore Route (to check if Firestore connection works) ---
@app.route('/test_firestore')
def test_firestore():
    try:
        # Try to write a simple document to a test collection
        doc_ref = db.collection('backend_test_data').document('connection_status')
        doc_ref.set({
            'message': 'Hello from Flask to Firestore! Connection successful.',
            'timestamp': firestore.SERVER_TIMESTAMP # This adds the server's timestamp
        })
        return jsonify({"status": "success", "message": "Firestore write successful. Check your 'backend_test_data' collection in Firebase Console!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Get User Data Endpoint ---
@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    # In a real app, you'd get user_id from authentication.
    user_id = "test_user_001" # Still using placeholder for MVP

    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        # If user doesn't exist, create a default one (same logic as in pull_gacha)
        initial_user_data = {
            "star_night_crystals": 5000,
            "owned_characters": [],
            "gacha_pity_4_star": 0,
            "gacha_pity_5_star": 0
        }
        user_ref.set(initial_user_data)
        return jsonify(initial_user_data), 200
    else:
        return jsonify(user_doc.to_dict()), 200

# --- Gacha Pull Endpoint ---
@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    # In a real app, you'd get user_id from authentication, e.g., from Telegram Mini App data.
    # For now, let's use a placeholder user ID.
    user_id = "test_user_001"
    
    # Get user data from Firestore
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        # If user doesn't exist, create a default one for testing
        user_data = {
            "star_night_crystals": 5000, # Give them some starting currency
            "owned_characters": [],
            "gacha_pity_4_star": 0,
            "gacha_pacha_5_star": 0
        }
        user_ref.set(user_data)
    else:
        user_data = user_doc.to_dict()

    # Determine pull type (single or multi) - for now, let's default to single for testing
    # Later, this will come from the request JSON
    pull_type = request.json.get('pull_type', 'single') if request.is_json else 'single'

    if pull_type == 'single':
        cost = GACHA_CONFIG["pull_cost_single"]
        num_pulls = 1
    elif pull_type == 'multi':
        cost = GACHA_CONFIG["pull_cost_multi"]
        num_pulls = 10
    else:
        return jsonify({"status": "error", "message": "Invalid pull type."}), 400

    if user_data["star_night_crystals"] < cost:
        return jsonify({"status": "error", "message": "Not enough StarNight Crystals."}), 400

    pulled_characters = []
    current_4_star_pity = user_data.get("gacha_pity_4_star", 0)
    current_5_star_pity = user_data.get("gacha_pity_5_star", 0)

    for _ in range(num_pulls):
        pulled_char, new_4_pity, new_5_pity = perform_single_pull(current_4_star_pity, current_5_star_pity)
        pulled_characters.append(pulled_char)
        current_4_star_pity = new_4_pity
        current_5_star_pity = new_5_pity
        
        # Add the pulled character's ID to the user's owned characters (simplistic for now)
        user_data["owned_characters"].append(pulled_char["id"])


    # Update user data in Firestore
    user_data["star_night_crystals"] -= cost
    user_data["gacha_pity_4_star"] = current_4_star_pity
    user_data["gacha_pity_5_star"] = current_5_star_pity

    # Use a transaction to ensure atomic updates if multiple pulls happen simultaneously (good practice)
    try:
        @firestore.transactional
        def update_user_transaction(transaction, user_ref, user_data_to_update):
            snapshot = user_ref.get(transaction=transaction)
            if not snapshot.exists:
                raise Exception("User document did not exist during transaction.")
            transaction.update(user_ref, user_data_to_update)

        transaction = db.transaction()
        update_user_transaction(transaction, user_ref, user_data)
        
        return jsonify({
            "status": "success",
            "message": f"Successfully performed {num_pulls} pull(s).",
            "pulled_characters": pulled_characters,
            "remaining_crystals": user_data["star_night_crystals"],
            "new_pity_4_star": user_data["gacha_pity_4_star"],
            "new_pity_5_star": user_data["gacha_pity_5_star"]
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to update user data: {str(e)}"}), 500

# --- Run the Flask App ---
if __name__ == '__main__':
    # Render provides the PORT as an environment variable
    port = int(os.environ.get("PORT", 5000)) # Default to 5000 for local dev
    app.run(debug=True, host='0.0.0.0', port=port)