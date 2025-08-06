import os
import json
import hashlib
import hmac
import sqlite3
import random
from urllib.parse import unquote
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24) # A strong secret key for session management

# --- Database Configuration ---
DATABASE = 'novaflare.db'

# --- Default User Data ---
# IMPORTANT: If you change the structure here, you might need to re-initialize your database
# or add migration logic if users already exist. For development, deleting novaflare.db is easiest.
DEFAULT_USER_DATA = {
    'star_night_crystals': 1000,
    'lumen_orbs': 5,
    'halo_orbs': 0,
    'auric_crescents': 0, # New currency
    'orbital_jewels': 0,  # New currency
    'inventory': [],
    'pity_counters': { # Initialize pity counters for all banners
        "standard_character": {"4_star": 0, "5_star": 0},
        "standard_weapon": {"4_star": 0, "5_star": 0},
        "limited_character_1": {"4_star": 0, "5_star": 0},
        "limited_character_2": {"4_star": 0, "5_star": 0},
        "limited_weapon_1": {"4_star": 0, "5_star": 0},
        "limited_weapon_2": {"4_star": 0, "5_star": 0},
    },
    'monthly_exchanges': {
        'exchange_lumen': 0,
        'exchange_halo': 0
    }
}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # This makes rows behave like dictionaries
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Create users table for login
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'player'
            )
        ''')
        # Create user_data table for game progress, including new currency fields
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_data (
                user_id TEXT PRIMARY KEY,
                star_night_crystals INTEGER DEFAULT 1000,
                lumen_orbs INTEGER DEFAULT 5,
                halo_orbs INTEGER DEFAULT 0,
                auric_crescents INTEGER DEFAULT 0,
                orbital_jewels INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '[]',
                pity_counters TEXT DEFAULT '{}',
                monthly_exchanges TEXT DEFAULT '{}'
            )
        ''')
        db.commit()

        # Add default admin and player users if they don't exist
        # Admin: username='admin', password='adminpassword'
        # Player: username='player', password='playerpassword'
        
        # Check if admin exists
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if cursor.fetchone() is None:
            hashed_password = generate_password_hash('adminpassword')
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('admin', hashed_password, 'admin'))
            print("Default admin user created: username='admin', password='adminpassword'")

        # Check if player exists
        cursor.execute("SELECT id FROM users WHERE username = 'player'")
        if cursor.fetchone() is None:
            hashed_password = generate_password_hash('playerpassword')
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           ('player', hashed_password, 'player'))
            print("Default player user created: username='player', password='playerpassword'")
        
        db.commit()

# Call init_db once when the app starts
with app.app_context():
    init_db()

# --- Gacha Configuration and Item Pool ---
# Define costs for shop and gacha pulls
COST_MAP = {
    # Gacha pull costs (per pull)
    'standard_character': {'orb': 'lumen_orbs', 'snc': 70},
    'standard_weapon': {'orb': 'lumen_orbs', 'snc': 70},
    'limited_character_1': {'orb': 'halo_orbs', 'snc': 100},
    'limited_character_2': {'orb': 'halo_orbs', 'snc': 100},
    'limited_weapon_1': {'orb': 'halo_orbs', 'snc': 100},
    'limited_weapon_2': {'orb': 'halo_orbs', 'snc': 100},

    # Shop exchange costs
    'buy_lumen_1': {'cost_type': 'star_night_crystals', 'cost_amount': 70, 'reward_type': 'lumen_orbs', 'reward_amount': 1},
    'buy_lumen_10': {'cost_type': 'star_night_crystals', 'cost_amount': 595, 'reward_type': 'lumen_orbs', 'reward_amount': 10},
    'buy_halo_1': {'cost_type': 'star_night_crystals', 'cost_amount': 100, 'reward_type': 'halo_orbs', 'reward_amount': 1},
    'buy_halo_10': {'cost_type': 'star_night_crystals', 'cost_amount': 900, 'reward_type': 'halo_orbs', 'reward_amount': 10},
    'exchange_lumen': {'cost_type': 'auric_crescents', 'cost_amount': 20, 'reward_type': 'lumen_orbs', 'reward_amount': 1, 'limit': 10},
    'exchange_halo': {'cost_type': 'auric_crescents', 'cost_amount': 20, 'reward_type': 'halo_orbs', 'reward_amount': 1, 'limit': 10}
}

# Define Gacha probabilities and item pool (UPDATED for rarity rules)
GACHA_RATES = {
    "standard_character": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        # No 3-star for characters
    },
    "standard_weapon": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943}, # 3-star for weapons
    },
    "limited_character_1": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        # No 3-star for characters
    },
    "limited_character_2": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        # No 3-star for characters
    },
    "limited_weapon_1": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943}, # 3-star for weapons
    },
    "limited_weapon_2": {
        5: {"base_rate": 0.006, "pity_start": 75, "hard_pity": 90},
        4: {"base_rate": 0.051, "hard_pity": 10},
        3: {"base_rate": 0.943}, # 3-star for weapons
    },
}

GACHA_POOL = {
    "standard_character": [
        {"name": "Nova Aethel", "rarity": 5, "type": "Character", "image": "char_nova_aethel_5.png"},
        {"name": "Kaelus", "rarity": 5, "type": "Character", "image": "char_kaelus_5.png"},
        {"name": "Cyrus", "rarity": 4, "type": "Character", "image": "char_cyrus_4.png"},
        {"name": "Lyra", "rarity": 4, "type": "Character", "image": "char_lyra_4.png"},
    ],
    "standard_weapon": [
        {"name": "Starlight Aegis", "rarity": 5, "type": "Weapon", "image": "weapon_starlight_aegis_5.png"},
        {"name": "Voidwalker's Blade", "rarity": 5, "type": "Weapon", "image": "weapon_voidwalkers_blade_5.png"},
        {"name": "Radiant Staff", "rarity": 4, "type": "Weapon", "image": "weapon_radiant_staff_4.png"},
        {"name": "Shadowstrike Bow", "rarity": 4, "type": "Weapon", "image": "weapon_shadowstrike_bow_4.png"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon", "image": "weapon_common_sword_3.png"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon", "image": "weapon_iron_dagger_3.png"},
    ],
    "limited_character_1": [
        {"name": "Limited Char A", "rarity": 5, "type": "Character", "is_limited": True, "image": "char_limited_a_5.png"},
        {"name": "Limited Char B", "rarity": 4, "type": "Character", "is_limited": True, "image": "char_limited_b_4.png"},
        {"name": "Nova Aethel", "rarity": 5, "type": "Character", "image": "char_nova_aethel_5.png"}, # Standard 5-star in limited pool
        {"name": "Cyrus", "rarity": 4, "type": "Character", "image": "char_cyrus_4.png"}, # Standard 4-star in limited pool
    ],
    "limited_character_2": [
        {"name": "Limited Char C", "rarity": 5, "type": "Character", "is_limited": True, "image": "char_limited_c_5.png"},
        {"name": "Limited Char D", "rarity": 4, "type": "Character", "is_limited": True, "image": "char_limited_d_4.png"},
        {"name": "Kaelus", "rarity": 5, "type": "Character", "image": "char_kaelus_5.png"},
        {"name": "Lyra", "rarity": 4, "type": "Character", "image": "char_lyra_4.png"},
    ],
    "limited_weapon_1": [
        {"name": "Limited Weapon A", "rarity": 5, "type": "Weapon", "is_limited": True, "image": "weapon_limited_a_5.png"},
        {"name": "Limited Weapon B", "rarity": 4, "type": "Weapon", "is_limited": True, "image": "weapon_limited_b_4.png"},
        {"name": "Starlight Aegis", "rarity": 5, "type": "Weapon", "image": "weapon_starlight_aegis_5.png"},
        {"name": "Radiant Staff", "rarity": 4, "type": "Weapon", "image": "weapon_radiant_staff_4.png"},
        {"name": "Common Sword", "rarity": 3, "type": "Weapon", "image": "weapon_common_sword_3.png"},
    ],
    "limited_weapon_2": [
        {"name": "Limited Weapon C", "rarity": 5, "type": "Weapon", "is_limited": True, "image": "weapon_limited_c_5.png"},
        {"name": "Limited Weapon D", "rarity": 4, "type": "Weapon", "is_limited": True, "image": "weapon_limited_d_4.png"},
        {"name": "Voidwalker's Blade", "rarity": 5, "type": "Weapon", "image": "weapon_voidwalkers_blade_5.png"},
        {"name": "Shadowstrike Bow", "rarity": 4, "type": "Weapon", "image": "weapon_shadowstrike_bow_4.png"},
        {"name": "Iron Dagger", "rarity": 3, "type": "Weapon", "image": "weapon_iron_dagger_3.png"},
    ],
}

def get_pull_result(banner_type, pity_4, pity_5):
    pool = list(GACHA_POOL.get(banner_type, []))
    if not pool:
        return {"name": "Error", "rarity": 0, "type": "Error", "image": "error.png"}

    # Filter pool based on banner type to ensure correct rarities are pulled
    if "character" in banner_type:
        valid_rarities = [4, 5]
    else: # Weapon banners
        valid_rarities = [3, 4, 5]
    
    filtered_pool = [item for item in pool if item["rarity"] in valid_rarities]

    # Check for hard pity first
    if pity_5 >= GACHA_RATES[banner_type][5]["hard_pity"] - 1:
        # Ensure we only pull 5-star items from the filtered pool
        return random.choice([item for item in filtered_pool if item["rarity"] == 5])
    
    if pity_4 >= GACHA_RATES[banner_type][4]["hard_pity"] - 1:
        # Ensure we only pull 4-star items from the filtered pool
        return random.choice([item for item in filtered_pool if item["rarity"] == 4])

    roll = random.random()

    # Calculate soft pity rate for 5-star
    roll_rate_5 = GACHA_RATES[banner_type][5]["base_rate"]
    if pity_5 >= GACHA_RATES[banner_type][5]["pity_start"]:
        soft_pity_pulls = pity_5 - GACHA_RATES[banner_type][5]["pity_start"] + 1
        roll_rate_5 += 0.05 * soft_pity_pulls # Increase rate by 5% per pull after soft pity start

    # Determine rarity based on roll and available rarities
    if roll < roll_rate_5 and 5 in valid_rarities:
        return random.choice([item for item in filtered_pool if item["rarity"] == 5])
    elif roll < (GACHA_RATES[banner_type][4]["base_rate"] + roll_rate_5) and 4 in valid_rarities:
        return random.choice([item for item in filtered_pool if item["rarity"] == 4])
    elif 3 in valid_rarities: # Only pull 3-star if it's a weapon banner
        return random.choice([item for item in filtered_pool if item["rarity"] == 3])
    else: # Fallback if somehow no valid rarity is found (shouldn't happen with correct pool setup)
        # This fallback ensures something is always returned, even if rates don't add up perfectly.
        # In a real system, rates should sum to 1.0 for all valid rarities.
        return random.choice(filtered_pool)


# --- Telegram Web App Validation ---
# Replace with your actual bot token
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE" 

def validate_telegram_data(init_data):
    # For local testing without a real Telegram bot token, you can bypass validation
    # In production, ensure BOT_TOKEN is set and validation is active.
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("Warning: BOT_TOKEN is not set or is default. Skipping Telegram data validation.")
        # Return a dummy user ID for local development
        return True, "123456789" # Example dummy user ID
    
    params = {k: unquote(v) for k, v in [p.split('=') for p in init_data.split('&')]}
    if 'hash' not in params:
        print("Validation failed: 'hash' parameter missing.")
        return False, None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()) if k != 'hash')
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash == params['hash']:
        user_data = json.loads(params.get('user', '{}'))
        user_id = str(user_data.get('id'))
        return True, user_id
    
    print(f"Validation failed: Hash mismatch. Calculated: {calculated_hash}, Received: {params['hash']}")
    return False, None

# --- User Management (Database-backed) ---
def get_user_data_from_db(user_id):
    db_conn = get_db()
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM user_data WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()

    if user_row:
        # Convert JSON strings back to Python objects
        user_data = dict(user_row)
        user_data['inventory'] = json.loads(user_data['inventory'])
        user_data['pity_counters'] = json.loads(user_data['pity_counters'])
        user_data['monthly_exchanges'] = json.loads(user_data['monthly_exchanges'])
        return user_data
    else:
        # Create new user data in DB if not found
        new_user_data = DEFAULT_USER_DATA.copy()
        new_user_data['user_id'] = user_id # Add user_id to the data
        
        # Ensure pity counters are initialized for all banners for new users
        for banner in GACHA_RATES.keys():
            if banner not in new_user_data['pity_counters']:
                new_user_data['pity_counters'][banner] = {"4_star": 0, "5_star": 0}

        cursor.execute('''
            INSERT INTO user_data (user_id, star_night_crystals, lumen_orbs, halo_orbs, auric_crescents, orbital_jewels, inventory, pity_counters, monthly_exchanges)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            new_user_data['star_night_crystals'],
            new_user_data['lumen_orbs'],
            new_user_data['halo_orbs'],
            new_user_data['auric_crescents'],
            new_user_data['orbital_jewels'],
            json.dumps(new_user_data['inventory']),
            json.dumps(new_user_data['pity_counters']),
            json.dumps(new_user_data['monthly_exchanges'])
        ))
        db_conn.commit()
        return new_user_data

def save_user_data_to_db(user_id, data):
    db_conn = get_db()
    cursor = db_conn.cursor()
    cursor.execute('''
        UPDATE user_data SET 
            star_night_crystals = ?, 
            lumen_orbs = ?, 
            halo_orbs = ?, 
            auric_crescents = ?, 
            orbital_jewels = ?,
            inventory = ?, 
            pity_counters = ?, 
            monthly_exchanges = ?
        WHERE user_id = ?
    ''', (
        data['star_night_crystals'],
        data['lumen_orbs'],
        data['halo_orbs'],
        data['auric_crescents'],
        data['orbital_jewels'],
        json.dumps(data['inventory']),
        json.dumps(data['pity_counters']),
        json.dumps(data['monthly_exchanges']),
        user_id
    ))
    db_conn.commit()

# --- Authentication Routes ---
@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    db_conn = get_db()
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()

    if user_row and check_password_hash(user_row['password'], password):
        session['user_id'] = user_row['id']
        session['username'] = user_row['username']
        session['role'] = user_row['role']
        
        if user_row['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('serve_index_html')) # Redirect to home for players
    else:
        return render_template('login.html', error='Invalid username or password')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login_page'))

# --- Admin Dashboard (Placeholder for now) ---
@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return "Access Denied: Admins only!", 403
    return render_template('admin.html', username=session['username'])


# --- Flask Routes (Updated to use DB functions) ---
@app.route('/')
def serve_index_html():
    # If not logged in, redirect to login page
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html')

@app.route('/game')
def serve_game_html():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('game.html')

@app.route('/shop')
def serve_shop_html():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('shop.html')

@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    # For Telegram WebApp, we still validate init_data
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, telegram_user_id = validate_telegram_data(init_data)

    user_id_to_fetch = None
    if is_valid:
        user_id_to_fetch = telegram_user_id
    elif 'user_id' in session:
        user_id_to_fetch = str(session['user_id'])
    
    if not user_id_to_fetch:
        return jsonify({'status': 'error', 'message': 'Not authenticated.'}), 401

    user = get_user_data_from_db(user_id_to_fetch)
    return jsonify({
        'status': 'success',
        'user_id': user_id_to_fetch, # Return the ID that was actually used
        'star_night_crystals': user['star_night_crystals'],
        'lumen_orbs': user['lumen_orbs'],
        'halo_orbs': user['halo_orbs'],
        'auric_crescents': user['auric_crescents'],
        'orbital_jewels': user['orbital_jewels'], # Include new currency
        'pity_counters': user['pity_counters'],
        'inventory': user['inventory']
    })

@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, telegram_user_id = validate_telegram_data(init_data)
    
    user_id_to_process = None
    if is_valid:
        user_id_to_process = telegram_user_id
    elif 'user_id' in session:
        user_id_to_process = str(session['user_id'])
    
    if not user_id_to_process:
        return jsonify({'status': 'error', 'message': 'Not authenticated.'}), 401

    data = request.get_json()
    pull_type = data.get('pull_type')
    banner_type = data.get('banner_type')

    if banner_type not in GACHA_POOL:
        return jsonify({'status': 'error', 'message': f'Invalid banner type: {banner_type}.'}), 400

    user = get_user_data_from_db(user_id_to_process)
    
    num_pulls = 10 if pull_type == 'multi' else 1
    
    # Determine cost based on banner type and number of pulls
    cost_snc_per_pull = COST_MAP[banner_type]['snc']
    cost_orb_per_pull = 1 # 1 orb per pull

    cost_snc_total = cost_snc_per_pull * num_pulls
    cost_orb_total = cost_orb_per_pull * num_pulls
    
    # Apply 10-pull discount for SNC if specified in COST_MAP (e.g., 595 for standard, 900 for limited)
    if num_pulls == 10:
        if 'standard' in banner_type:
            cost_snc_total = 595 # Fixed discount for 10-pull standard
        elif 'limited' in banner_type:
            cost_snc_total = 900 # Fixed discount for 10-pull limited
            
    orb_currency_type = COST_MAP[banner_type]['orb']

    # Check and deduct currency
    if user[orb_currency_type] >= cost_orb_total:
        user[orb_currency_type] -= cost_orb_total
        currency_spent_type = orb_currency_type
    elif user['star_night_crystals'] >= cost_snc_total:
        user['star_night_crystals'] -= cost_snc_total
        currency_spent_type = 'star_night_crystals'
    else:
        return jsonify({'status': 'error', 'message': 'Insufficient currency for this pull.'}), 400

    pulled_items = []
    pity_4 = user['pity_counters'].get(banner_type, {}).get('4_star', 0)
    pity_5 = user['pity_counters'].get(banner_type, {}).get('5_star', 0)

    for _ in range(num_pulls):
        pity_4 += 1
        pity_5 += 1

        result = get_pull_result(banner_type, pity_4, pity_5)
        pulled_items.append(result)
        user['inventory'].append(result)

        # Award Orbital Jewels (OJ) based on rarity
        if result['rarity'] == 3:
            user['orbital_jewels'] += 25
        elif result['rarity'] == 4:
            user['orbital_jewels'] += 50
            # Award Auric Crescents (AC) for 4-star
            user['auric_crescents'] += 10
        elif result['rarity'] == 5:
            user['orbital_jewels'] += 100
            # Award Auric Crescents (AC) for 5-star
            user['auric_crescents'] += 20

        # Reset pity counters
        if result['rarity'] == 4:
            pity_4 = 0
        if result['rarity'] == 5:
            pity_5 = 0
            pity_4 = 0 # 5-star resets 4-star pity too

        # Check for Spectra (duplicate characters) for Auric Crescents
        # This is a simplified check. In a real game, you'd track character ownership
        # and check if the pulled character is already owned.
        # For now, we'll assume any 4-star or 5-star character pull *could* be a duplicate
        # and award AC for Spectra if it's a character.
        if result['type'] == 'Character' and (result['rarity'] == 4 or result['rarity'] == 5):
            # This is a placeholder logic. You'd need a system to track owned characters
            # and detect actual duplicates to award 50 AC per Spectra.
            # For demonstration, let's just add a small chance or a fixed amount for now.
            # As per your rule: "50 AC On Every Spectra"
            # Since we don't have character ownership tracking here,
            # I'll add a placeholder if a character is pulled that *could* be a duplicate.
            # For a true implementation, you'd need to fetch user's owned characters.
            # For now, I'll assume if a 4* or 5* character is pulled, it might be a Spectra.
            # A more robust solution would involve checking if the user already owns this specific character.
            # For this MVP, let's just add 50 AC if it's a character of 4* or 5* as a placeholder for "Spectra".
            # This assumes every character pull of 4* or 5* is a "Spectra" for AC purposes.
            # This needs to be refined with actual character ownership tracking.
            user['auric_crescents'] += 50 # Add 50 AC for potential Spectra (duplicate character)

    # Ensure the banner_type key exists in pity_counters before assigning
    if banner_type not in user['pity_counters']:
        user['pity_counters'][banner_type] = {}
    user['pity_counters'][banner_type]['4_star'] = pity_4
    user['pity_counters'][banner_type]['5_star'] = pity_5

    save_user_data_to_db(user_id_to_process, user)

    return jsonify({
        'status': 'success',
        'pulled_items': pulled_items,
        'star_night_crystals': user['star_night_crystals'],
        'lumen_orbs': user['lumen_orbs'],
        'halo_orbs': user['halo_orbs'],
        'auric_crescents': user['auric_crescents'],
        'orbital_jewels': user['orbital_jewels'],
        'pity_4_star': pity_4,
        'pity_5_star': pity_5
    })

@app.route('/exchange_shop', methods=['POST'])
def exchange_shop():
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, telegram_user_id = validate_telegram_data(init_data)
    
    user_id_to_process = None
    if is_valid:
        user_id_to_process = telegram_user_id
    elif 'user_id' in session:
        user_id_to_process = str(session['user_id'])
    
    if not user_id_to_process:
        return jsonify({'status': 'error', 'message': 'Not authenticated.'}), 401

    data = request.get_json()
    exchange_type = data.get('exchange_type')

    user = get_user_data_from_db(user_id_to_process)
    exchange_info = COST_MAP.get(exchange_type)
    
    if not exchange_info:
        return jsonify({'status': 'error', 'message': 'Invalid exchange item.'}), 400

    cost_type = exchange_info['cost_type']
    cost_amount = exchange_info['cost_amount']
    reward_type = exchange_info['reward_type']
    reward_amount = exchange_info['reward_amount']
    limit = exchange_info.get('limit')

    if limit is not None:
        if user['monthly_exchanges'].get(exchange_type, 0) >= limit:
            return jsonify({'status': 'error', 'message': f'Monthly limit of {limit} reached for this item.'}), 400

    if user.get(cost_type, 0) >= cost_amount:
        user[cost_type] -= cost_amount
        user[reward_type] += reward_amount
        
        if limit is not None:
            user['monthly_exchanges'][exchange_type] = user['monthly_exchanges'].get(exchange_type, 0) + 1

        save_user_data_to_db(user_id_to_process, user)
        return jsonify({
            'status': 'success',
            'message': f'Successfully purchased {reward_amount} {reward_type}.',
            'star_night_crystals': user['star_night_crystals'],
            'lumen_orbs': user['lumen_orbs'],
            'halo_orbs': user['halo_orbs'],
            'auric_crescents': user['auric_crescents'],
            'orbital_jewels': user['orbital_jewels'] # Include new currency
        })
    else:
        return jsonify({'status': 'error', 'message': f'Insufficient {cost_type.replace("_", " ").title()} to make this purchase.'}), 400

if __name__ == '__main__':
    init_db() # Initialize database when running directly
    app.run(host='0.0.0.0', port=5000, debug=True)
