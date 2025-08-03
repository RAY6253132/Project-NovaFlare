from flask import Flask, request, jsonify
import json
import random

app = Flask(__name__)

# In-memory storage for user data. This is a default state.
# In a real application, you would use a database like Firestore or MongoDB.
user_data = {
    'star_night_crystals': 1200,
    'lumen_orbs': 5,
    'halo_orbs': 2,
    'auric_crescents': 50,
    'pity_counters': {
        'standard': {
            '4_star': 0,
            '5_star': 0
        },
        'limited': {
            '4_star': 0,
            '5_star': 0
        }
    }
}

# Dummy gacha item pool with rarity percentages
# This is a simplified model. In a real app, you would have a more detailed pool.
item_pool = {
    'standard': [
        {'name': 'Stardust Blade', 'rarity': 5, 'type': 'weapon', 'rate': 0.6},
        {'name': 'Galactic Sentinel', 'rarity': 5, 'type': 'character', 'rate': 0.6},
        {'name': 'Cosmic Gauntlets', 'rarity': 4, 'type': 'weapon', 'rate': 5.1},
        {'name': 'Void Shifter', 'rarity': 4, 'type': 'character', 'rate': 5.1},
        {'name': 'Iron Dagger', 'rarity': 3, 'type': 'weapon', 'rate': 88.6},
        {'name': 'Basic Armor', 'rarity': 3, 'type': 'armor', 'rate': 88.6}
    ],
    'limited': [
        {'name': 'Exalted Hero', 'rarity': 5, 'type': 'character', 'rate': 0.6},
        {'name': 'Dragon\'s Breath', 'rarity': 5, 'type': 'weapon', 'rate': 0.6},
        {'name': 'Shadow Weasel', 'rarity': 4, 'type': 'character', 'rate': 5.1},
        {'name': 'Spectral Bow', 'rarity': 4, 'type': 'weapon', 'rate': 5.1},
        {'name': 'Iron Dagger', 'rarity': 3, 'type': 'weapon', 'rate': 88.6},
        {'name': 'Basic Armor', 'rarity': 3, 'type': 'armor', 'rate': 88.6}
    ]
}

def get_item_by_rarity(rarity, banner_type):
    """
    Selects a random item from the pool based on rarity.
    """
    candidates = [item for item in item_pool[banner_type] if item['rarity'] == rarity]
    if candidates:
        return random.choice(candidates)
    return None

def roll_gacha_single(banner_type, pity_4_star, pity_5_star):
    """
    Simulates a single gacha pull with pity.
    Returns the pulled item and updated pity counters.
    """
    # Define pity thresholds
    PITY_4_STAR = 10
    PITY_5_STAR = 90

    # Pity logic
    if pity_5_star >= PITY_5_STAR:
        item = get_item_by_rarity(5, banner_type)
        return item, 0, pity_4_star + 1  # Reset 5-star pity
    elif pity_4_star >= PITY_4_STAR:
        item = get_item_by_rarity(4, banner_type)
        return item, pity_5_star + 1, 0  # Reset 4-star pity
    else:
        # Normal pull logic based on rates
        rates = {'5_star': 0.006, '4_star': 0.051, '3_star': 0.943}
        roll = random.random()
        if roll < rates['5_star']:
            item = get_item_by_rarity(5, banner_type)
            return item, 0, 0
        elif roll < rates['5_star'] + rates['4_star']:
            item = get_item_by_rarity(4, banner_type)
            return item, pity_5_star + 1, 0
        else:
            item = get_item_by_rarity(3, banner_type)
            return item, pity_5_star + 1, pity_4_star + 1

@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    """
    Fetches the user's currency and pity counter data with safe dictionary access.
    """
    try:
        # Safely get values from user_data with a default of 0 or an empty dict
        response_data = {
            'status': 'success',
            'star_night_crystals': user_data.get('star_night_crystals', 0),
            'lumen_orbs': user_data.get('lumen_orbs', 0),
            'halo_orbs': user_data.get('halo_orbs', 0),
            'auric_crescents': user_data.get('auric_crescents', 0),
            'pity_counters': user_data.get('pity_counters', {})
        }
        return jsonify(response_data)
    except Exception as e:
        # This catch block is for unexpected errors, but safe access should prevent KeyErrors
        return jsonify({
            'status': 'error',
            'message': f'Server-side error: {str(e)}'
        }), 500

@app.route('/pull_gacha', methods=['POST'])
def pull_gacha():
    """
    Simulates a gacha pull and updates user data with safe dictionary access.
    """
    data = request.json
    pull_type = data.get('pull_type')
    banner_type = data.get('banner_type')

    if banner_type not in item_pool or banner_type == 'limited':
        return jsonify({'status': 'error', 'message': 'Invalid or unavailable banner.'}), 400

    orb_cost = 10 if pull_type == 'multi' else 1
    snc_cost = 595 if pull_type == 'multi' else 70

    if banner_type == 'standard':
        orb_type = 'lumen_orbs'
    else:
        orb_type = 'halo_orbs'

    # Safely check and update user currencies
    current_orbs = user_data.get(orb_type, 0)
    current_snc = user_data.get('star_night_crystals', 0)

    if current_orbs >= orb_cost:
        user_data[orb_type] -= orb_cost
    elif current_snc >= snc_cost:
        user_data['star_night_crystals'] -= snc_cost
    else:
        return jsonify({'status': 'error', 'message': 'Insufficient currency.'}), 400

    pulled_items = []
    pity_4_star = user_data.get('pity_counters', {}).get(banner_type, {}).get('4_star', 0)
    pity_5_star = user_data.get('pity_counters', {}).get(banner_type, {}).get('5_star', 0)

    num_pulls = 10 if pull_type == 'multi' else 1
    
    # Perform the rolls
    for _ in range(num_pulls):
        item, new_pity_5, new_pity_4 = roll_gacha_single(banner_type, pity_4_star, pity_5_star)
        pulled_items.append(item)
        pity_4_star = new_pity_4
        pity_5_star = new_pity_5

    # Update pity counters
    if 'pity_counters' not in user_data:
        user_data['pity_counters'] = {}
    if banner_type not in user_data['pity_counters']:
        user_data['pity_counters'][banner_type] = {}

    user_data['pity_counters'][banner_type]['4_star'] = pity_4_star
    user_data['pity_counters'][banner_type]['5_star'] = pity_5_star

    return jsonify({
        'status': 'success',
        'pulled_items': pulled_items,
        'remaining_crystals': user_data.get('star_night_crystals', 0),
        'remaining_lumen_orbs': user_data.get('lumen_orbs', 0),
        'remaining_halo_orbs': user_data.get('halo_orbs', 0),
        'remaining_auric_crescents': user_data.get('auric_crescents', 0),
        'pity_4_star': pity_4_star,
        'pity_5_star': pity_5_star
    })

@app.route('/exchange_shop', methods=['POST'])
def exchange_shop():
    """
    Handles currency exchanges from the shop with safe dictionary access.
    """
    data = request.json
    exchange_type = data.get('exchange_type')

    # Exchange logic with safe currency checks
    current_snc = user_data.get('star_night_crystals', 0)
    current_ac = user_data.get('auric_crescents', 0)

    if exchange_type == 'buy_lumen_1' and current_snc >= 70:
        user_data['star_night_crystals'] -= 70
        user_data['lumen_orbs'] = user_data.get('lumen_orbs', 0) + 1
    elif exchange_type == 'buy_lumen_10' and current_snc >= 595:
        user_data['star_night_crystals'] -= 595
        user_data['lumen_orbs'] = user_data.get('lumen_orbs', 0) + 10
    elif exchange_type == 'buy_halo_1' and current_snc >= 100:
        user_data['star_night_crystals'] -= 100
        user_data['halo_orbs'] = user_data.get('halo_orbs', 0) + 1
    elif exchange_type == 'buy_halo_10' and current_snc >= 900:
        user_data['star_night_crystals'] -= 900
        user_data['halo_orbs'] = user_data.get('halo_orbs', 0) + 10
    elif exchange_type == 'exchange_lumen' and current_ac >= 20:
        user_data['auric_crescents'] -= 20
        user_data['lumen_orbs'] = user_data.get('lumen_orbs', 0) + 1
    elif exchange_type == 'exchange_halo' and current_ac >= 20:
        user_data['auric_crescents'] -= 20
        user_data['halo_orbs'] = user_data.get('halo_orbs', 0) + 1
    else:
        return jsonify({'status': 'error', 'message': 'Insufficient currency for exchange.'}), 400

    return jsonify({
        'status': 'success',
        'star_night_crystals': user_data.get('star_night_crystals', 0),
        'lumen_orbs': user_data.get('lumen_orbs', 0),
        'halo_orbs': user_data.get('halo_orbs', 0),
        'auric_crescents': user_data.get('auric_crescents', 0)
    })

if __name__ == '__main__':
    app.run(debug=True)
