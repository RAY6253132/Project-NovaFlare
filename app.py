import os
import json
import hashlib
import hmac
from urllib.parse import unquote
from flask import Flask, request, jsonify, render_template, session

app = Flask(__name__)
# A secret key is required for session management.
# In a real application, this should be a complex, random value from an environment variable.
app.secret_key = os.urandom(24)

# --- Dummy Database and Game Data ---
# In a real application, this would be a persistent database (e.g., PostgreSQL, SQLite).
# We'll use a simple in-memory dictionary for demonstration purposes.
db = {}

# Initial user data for new players
DEFAULT_USER_DATA = {
    'star_night_crystals': 1000,
    'lumen_orbs': 5,
    'halo_orbs': 0,
    'auric_crescents': 0,
    'inventory': [],
    'monthly_exchanges': {
        'exchange_lumen': 0,
        'exchange_halo': 0
    }
}

# Define costs for shop and gacha pulls
COST_MAP = {
    'standard': {'orb': 'lumen_orbs', 'snc': 70},
    'limited': {'orb': 'halo_orbs', 'snc': 100},
    'buy_lumen_1': {'cost_type': 'star_night_crystals', 'cost_amount': 70, 'reward_type': 'lumen_orbs', 'reward_amount': 1},
    'buy_lumen_10': {'cost_type': 'star_night_crystals', 'cost_amount': 595, 'reward_type': 'lumen_orbs', 'reward_amount': 10},
    'buy_halo_1': {'cost_type': 'star_night_crystals', 'cost_amount': 100, 'reward_type': 'halo_orbs', 'reward_amount': 1},
    'buy_halo_10': {'cost_type': 'star_night_crystals', 'cost_amount': 900, 'reward_type': 'halo_orbs', 'reward_amount': 10},
    'exchange_lumen': {'cost_type': 'auric_crescents', 'cost_amount': 20, 'reward_type': 'lumen_orbs', 'reward_amount': 1, 'limit': 10},
    'exchange_halo': {'cost_type': 'auric_crescents', 'cost_amount': 20, 'reward_type': 'halo_orbs', 'reward_amount': 1, 'limit': 10}
}

# Define gacha pool probabilities and items
GACHA_POOL = {
    'standard': [
        {'id': 'item_s_1', 'rarity': 'SSR', 'chance': 0.05},
        {'id': 'item_s_2', 'rarity': 'SR', 'chance': 0.25},
        {'id': 'item_s_3', 'rarity': 'R', 'chance': 0.70},
    ],
    'limited': [
        {'id': 'item_l_1', 'rarity': 'SSR', 'chance': 0.01},
        {'id': 'item_l_2', 'rarity': 'SR', 'chance': 0.15},
        {'id': 'item_l_3', 'rarity': 'R', 'chance': 0.84},
    ]
}

# --- Telegram Web App Validation ---
# Replace with your actual bot token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" 

def validate_telegram_data(init_data):
    if not BOT_TOKEN:
        print("Warning: BOT_TOKEN is not set. Skipping Telegram data validation.")
        return True, "12345" # A dummy user ID for local testing

    params = {k: unquote(v) for k, v in [p.split('=') for p in init_data.split('&')]}
    if 'hash' not in params:
        return False, None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()) if k != 'hash')
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash == params['hash']:
        user_data = json.loads(params.get('user', '{}'))
        user_id = str(user_data.get('id'))
        return True, user_id
    
    return False, None

# --- User Management ---
def get_user(user_id):
    if user_id not in db:
        db[user_id] = DEFAULT_USER_DATA.copy()
    return db[user_id]

def save_user(user_id, data):
    db[user_id] = data

# --- API Endpoints ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/game')
def game():
    return render_template('game.html')

@app.route('/shop')
def shop():
    return render_template('shop.html')

@app.route('/get_user_data')
def get_user_data():
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, user_id = validate_telegram_data(init_data)

    if not is_valid:
        return jsonify({'status': 'error', 'message': 'Invalid Telegram data'}), 401
    
    user = get_user(user_id)
    return jsonify({'status': 'success', **user})

@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, user_id = validate_telegram_data(init_data)
    if not is_valid:
        return jsonify({'status': 'error', 'message': 'Invalid Telegram data'}), 401

    data = request.get_json()
    banner_type = data.get('banner_type')
    num_pulls = data.get('num_pulls', 1)

    user = get_user(user_id)
    banner_info = COST_MAP.get(banner_type)

    if not banner_info:
        return jsonify({'status': 'error', 'message': 'Invalid banner type'}), 400

    orb_type = banner_info['orb']
    cost_snc = banner_info['snc'] * num_pulls
    cost_orb = num_pulls

    # Apply discounts for 10-pulls
    if num_pulls == 10:
        if banner_type == 'standard':
            cost_snc = 595
        elif banner_type == 'limited':
            cost_snc = 900
            
    if user[orb_type] >= cost_orb and user['star_night_crystals'] >= cost_snc:
        user[orb_type] -= cost_orb
        user['star_night_crystals'] -= cost_snc

        results = []
        for _ in range(num_pulls):
            # Simple gacha logic based on probabilities
            rand_roll = random.random()
            
            # This is a very basic implementation. Real gacha systems have "pity" counters, etc.
            current_chance = 0
            for item in GACHA_POOL[banner_type]:
                current_chance += item['chance']
                if rand_roll <= current_chance:
                    results.append(item['id'])
                    break
        
        user['inventory'].extend(results)
        save_user(user_id, user)

        return jsonify({'status': 'success', 'results': results, **user})
    else:
        return jsonify({'status': 'error', 'message': 'Insufficient currency for this pull.'}), 400

@app.route('/exchange_shop', methods=['POST'])
def exchange_shop():
    init_data = request.headers.get('X-Telegram-Init-Data')
    is_valid, user_id = validate_telegram_data(init_data)
    if not is_valid:
        return jsonify({'status': 'error', 'message': 'Invalid Telegram data'}), 401

    data = request.get_json()
    exchange_type = data.get('exchange_type')

    user = get_user(user_id)
    exchange_info = COST_MAP.get(exchange_type)
    
    if not exchange_info:
        return jsonify({'status': 'error', 'message': 'Invalid exchange item'}), 400

    cost_type = exchange_info['cost_type']
    cost_amount = exchange_info['cost_amount']
    reward_type = exchange_info['reward_type']
    reward_amount = exchange_info['reward_amount']
    limit = exchange_info.get('limit')

    # Check monthly limits
    if limit and user['monthly_exchanges'].get(exchange_type, 0) >= limit:
        return jsonify({'status': 'error', 'message': f'Monthly limit of {limit} reached for this item.'}), 400

    if user.get(cost_type, 0) >= cost_amount:
        user[cost_type] -= cost_amount
        user[reward_type] += reward_amount
        
        if limit:
            user['monthly_exchanges'][exchange_type] = user['monthly_exchanges'].get(exchange_type, 0) + 1

        save_user(user_id, user)
        return jsonify({'status': 'success', 'message': f'Successfully purchased {reward_amount} {reward_type}.', **user})
    else:
        return jsonify({'status': 'error', 'message': f'Insufficient {cost_type} to make this purchase.'}), 400


# To reset monthly limits, you would need a scheduled task that runs at the beginning of each month.
# Example pseudo-code for a task:
# def reset_monthly_limits():
#     for user_id in db:
#         db[user_id]['monthly_exchanges'] = {}

if __name__ == '__main__':
    # You might want to use a more production-ready server like Gunicorn or uWSGI
    # For development, you can use the built-in Flask server
    import random
    app.run(host='0.0.0.0', port=5000, debug=True)