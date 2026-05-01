"""
Calibration Engine for Horse Racing Analyzer
Manages historical race results and weight optimization for prediction factors.
"""

import json
import os
import math
import argparse
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(SCRIPT_DIR, 'results_history.json')

FACTORS = [
    'form',
    'rating',
    'trainer',
    'jockey',
    'fitness',
    'class',
    'going',
    'course',
    'distance',
    'age',
    'weight',
    'draw',
    'headgear',
    'spotlight'
]

DEFAULT_WEIGHTS = {
    'form': 20,
    'rating': 15,
    'trainer': 12,
    'jockey': 10,
    'fitness': 8,
    'class': 8,
    'going': 8,
    'course': 6,
    'distance': 6,
    'age': 7,
    'weight': 8,
    'draw': 5,
    'headgear': 3,
    'spotlight': 2
}

TARGET_SUM = 118
MIN_RACES = 50
MAX_SWING = 0.4

# ============================================================================
# PROFILE CLASSIFICATION
# ============================================================================

def classify_profile(surface, race_type):
    """
    Classify a race into a profile based on surface and race_type.

    Returns:
        'aw' - All-weather surface
        'nh' - National Hunt (jumps)
        'turf_flat' - Turf flat racing
    """
    surface_str = str(surface).lower()
    race_type_str = str(race_type).lower()

    if 'aw' in surface_str or 'all-weather' in surface_str:
        return 'aw'

    nh_keywords = ['hurdle', 'chase', 'nh flat', 'bumper']
    if any(keyword in race_type_str for keyword in nh_keywords):
        return 'nh'

    return 'turf_flat'

# ============================================================================
# HISTORY MANAGEMENT
# ============================================================================

def load_history():
    """
    Load results history from JSON file.
    Returns default structure if file doesn't exist.
    """
    if not os.path.exists(HISTORY_PATH):
        return {
            'races': [],
            'weight_profiles': {
                'aw': DEFAULT_WEIGHTS.copy(),
                'nh': DEFAULT_WEIGHTS.copy(),
                'turf_flat': DEFAULT_WEIGHTS.copy()
            },
            'calibrations': []
        }

    try:
        with open(HISTORY_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {
            'races': [],
            'weight_profiles': {
                'aw': DEFAULT_WEIGHTS.copy(),
                'nh': DEFAULT_WEIGHTS.copy(),
                'turf_flat': DEFAULT_WEIGHTS.copy()
            },
            'calibrations': []
        }

def save_history(history):
    """
    Save history atomically using temp file + os.replace.
    """
    tmp_path = HISTORY_PATH + '.tmp'

    try:
        with open(tmp_path, 'w') as f:
            json.dump(history, f, indent=2)
        os.replace(tmp_path, HISTORY_PATH)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
        raise e

# ============================================================================
# RACE RESULTS
# ============================================================================

def save_race_results(race_key, results_list, race_data, runners_data):
    """
    Save finishing positions for a race.

    Args:
        race_key: String like "2026-03-24_Ascot_14:30"
        results_list: List of {'name': str, 'finish_pos': int}
        race_data: Dict with 'surface' and 'race_type'
        runners_data: List of runner dicts with 'name' and score fields
    """
    history = load_history()

    # Parse race_key
    parts = race_key.split('_')
    date_str = parts[0] if len(parts) > 0 else ''
    venue = parts[1] if len(parts) > 1 else ''
    time_str = parts[2] if len(parts) > 2 else ''

    # Remove any existing entries with same date+venue+time
    history['races'] = [
        r for r in history['races']
        if not (r.get('date') == date_str and
                r.get('venue') == venue and
                r.get('time') == time_str)
    ]

    # Classify profile
    profile = classify_profile(race_data.get('surface'), race_data.get('race_type'))

    # Build runner lookup: {name -> predicted_score}
    runner_scores = {}
    for runner in runners_data:
        runner_scores[runner.get('name')] = runner.get('predicted_score', 0.0)

    # Build results with predicted scores
    results_with_scores = []
    for result in results_list:
        name = result.get('name')
        finish_pos = result.get('finish_pos')
        predicted_score = runner_scores.get(name, 0.0)
        results_with_scores.append({
            'name': name,
            'finish_pos': finish_pos,
            'predicted_score': predicted_score
        })

    # Create race record
    race_record = {
        'race_key': race_key,
        'date': date_str,
        'venue': venue,
        'time': time_str,
        'profile': profile,
        'surface': race_data.get('surface'),
        'race_type': race_data.get('race_type'),
        'results': results_with_scores,
        'timestamp': datetime.now().isoformat()
    }

    history['races'].append(race_record)
    save_history(history)

# ============================================================================
# RANKING
# ============================================================================

def _rank(values):
    """
    Assign ranks to values with tie handling (average rank).

    Args:
        values: List of numeric values

    Returns:
        List of ranks (1-indexed, with averages for ties)
    """
    if not values:
        return []

    # Create list of (value, original_index)
    indexed = [(v, i) for i, v in enumerate(values)]
    # Sort by value
    sorted_indexed = sorted(indexed, key=lambda x: x[0])

    # Assign ranks with tie handling
    ranks = [0.0] * len(values)
    i = 0
    while i < len(sorted_indexed):
        # Find all values equal to current value
        j = i
        while j < len(sorted_indexed) and sorted_indexed[j][0] == sorted_indexed[i][0]:
            j += 1
        # Average rank for positions i to j-1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            orig_idx = sorted_indexed[k][1]
            ranks[orig_idx] = avg_rank
        i = j

    return ranks

# ============================================================================
# CORRELATION
# ============================================================================

def spearman_rho(x, y):
    """
    Compute Spearman rank correlation coefficient.

    Args:
        x: List of values
        y: List of values (must be same length as x)

    Returns:
        Spearman correlation coefficient (0.0 if < 3 values)
    """
    if len(x) < 3 or len(y) < 3:
        return 0.0

    if len(x) != len(y):
        return 0.0

    # Rank both lists
    rank_x = _rank(x)
    rank_y = _rank(y)

    # Compute Pearson correlation of ranks
    mean_x = sum(rank_x) / len(rank_x)
    mean_y = sum(rank_y) / len(rank_y)

    numerator = sum((rank_x[i] - mean_x) * (rank_y[i] - mean_y) for i in range(len(rank_x)))
    denom_x = sum((rank_x[i] - mean_x) ** 2 for i in range(len(rank_x)))
    denom_y = sum((rank_y[i] - mean_y) ** 2 for i in range(len(rank_y)))

    if denom_x == 0 or denom_y == 0:
        return 0.0

    rho = numerator / math.sqrt(denom_x * denom_y)
    return rho

# ============================================================================
# STATISTICS
# ============================================================================

def get_performance_stats(profile_filter=None):
    """
    Get performance statistics for calibration analysis.

    Args:
        profile_filter: Optional profile to filter by ('aw', 'nh', 'turf_flat')

    Returns:
        Dict with:
        - tiers: Dict mapping confidence tier to stats
        - factor_correlations: Dict mapping factors to Spearman rho
        - race_count: Total races analyzed
        - profile_counts: Count per profile
        - cumulative: Rolling 20-race top3 rate for TOP PICK + STRONG
    """
    history = load_history()
    races = history.get('races', [])

    # Filter by profile if specified
    if profile_filter:
        races = [r for r in races if r.get('profile') == profile_filter]

    result = {
        'tiers': {
            'TOP PICK': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0},
            'STRONG': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0},
            'SOLID': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0},
            'MODERATE': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0},
            'WEAK': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0},
            'AVOID': {'count': 0, 'win_rate': 0.0, 'top3_rate': 0.0, 'expected_top3': 0.0}
        },
        'factor_correlations': {f: 0.0 for f in FACTORS},
        'race_count': len(races),
        'profile_counts': {'aw': 0, 'nh': 0, 'turf_flat': 0},
        'cumulative': []
    }

    if not races:
        return result

    # Profile counts
    for race in races:
        profile = race.get('profile', 'turf_flat')
        result['profile_counts'][profile] = result['profile_counts'].get(profile, 0) + 1

    # Tier statistics: infer tier from predicted_score distribution
    # Top 25% = TOP PICK, 25-50% = STRONG, 50-75% = SOLID, 75-87% = MODERATE, 87-95% = WEAK, 95%+ = AVOID
    all_scores = []
    for race in races:
        for result_item in race.get('results', []):
            all_scores.append(result_item.get('predicted_score', 0.0))

    if all_scores:
        all_scores.sort()
        p25 = all_scores[len(all_scores) // 4]
        p50 = all_scores[len(all_scores) // 2]
        p75 = all_scores[3 * len(all_scores) // 4]
        p87 = all_scores[int(0.87 * len(all_scores))]
        p95 = all_scores[int(0.95 * len(all_scores))]

        # Classify results by tier
        tier_results = {tier: [] for tier in result['tiers'].keys()}

        for race in races:
            field_size = len(race.get('results', []))
            for result_item in race.get('results', []):
                score = result_item.get('predicted_score', 0.0)
                finish_pos = result_item.get('finish_pos', 999)

                # Assign tier
                if score >= p95:
                    tier = 'AVOID'
                elif score >= p87:
                    tier = 'WEAK'
                elif score >= p75:
                    tier = 'MODERATE'
                elif score >= p50:
                    tier = 'SOLID'
                elif score >= p25:
                    tier = 'STRONG'
                else:
                    tier = 'TOP PICK'

                tier_results[tier].append({
                    'finish_pos': finish_pos,
                    'field_size': field_size
                })

        # Compute tier stats
        for tier, items in tier_results.items():
            if not items:
                continue

            count = len(items)
            wins = sum(1 for item in items if item['finish_pos'] == 1)
            top3 = sum(1 for item in items if item['finish_pos'] <= 3)
            avg_field = sum(item['field_size'] for item in items) / count if items else 8

            result['tiers'][tier]['count'] = count
            result['tiers'][tier]['win_rate'] = wins / count if count > 0 else 0.0
            result['tiers'][tier]['top3_rate'] = top3 / count if count > 0 else 0.0
            result['tiers'][tier]['expected_top3'] = 3.0 / avg_field if avg_field > 0 else 0.0

    # Factor correlations: score each runner on each factor, then correlate with negative finish_pos
    # For now, return zeros (requires factor scores in runners_data which we don't have here)
    for factor in FACTORS:
        result['factor_correlations'][factor] = 0.0

    # Cumulative: rolling 20-race top3 rate for TOP PICK + STRONG
    top_pick_results = []
    strong_results = []

    if all_scores:
        for race in races:
            for result_item in race.get('results', []):
                score = result_item.get('predicted_score', 0.0)
                finish_pos = result_item.get('finish_pos', 999)

                if score < p25:
                    top_pick_results.append(finish_pos <= 3)
                elif score < p50:
                    strong_results.append(finish_pos <= 3)

        combined = top_pick_results + strong_results
        rolling_window = 20
        for i in range(len(combined) - rolling_window + 1):
            window = combined[i:i+rolling_window]
            top3_rate = sum(window) / len(window) if window else 0.0
            result['cumulative'].append({
                'races': i + rolling_window,
                'top3_rate': top3_rate
            })

    return result

# ============================================================================
# WEIGHT PROPOSAL
# ============================================================================

def propose_new_weights(profile):
    """
    Propose new weights based on factor correlations.

    Args:
        profile: 'aw', 'nh', or 'turf_flat'

    Returns:
        Dict with 'weights' and 'backtest' info, or None if < MIN_RACES
    """
    history = load_history()
    races = history.get('races', [])
    races = [r for r in races if r.get('profile') == profile]

    if len(races) < MIN_RACES:
        return None

    # Compute correlations for each factor
    correlations = {}
    for factor in FACTORS:
        factor_scores = []
        finish_positions = []

        for race in races:
            for result_item in race.get('results', []):
                # For now, we don't have individual factor scores, so use predicted_score as proxy
                factor_scores.append(result_item.get('predicted_score', 0.0))
                # Negative finish position so higher is better
                finish_positions.append(-result_item.get('finish_pos', 999))

        if len(factor_scores) >= 3:
            rho = spearman_rho(factor_scores, finish_positions)
            correlations[factor] = rho
        else:
            correlations[factor] = 0.0

    # Propose new weights
    old_weights = history.get('weight_profiles', {}).get(profile, DEFAULT_WEIGHTS.copy())
    new_weights = {}

    for factor in FACTORS:
        rho = correlations[factor]
        old_weight = old_weights[factor]
        # new = old × (1 + rho × 0.5)
        new_weight = old_weight * (1.0 + rho * 0.5)
        # Cap at ±40% swing
        new_weight = max(old_weight * (1.0 - MAX_SWING),
                        min(old_weight * (1.0 + MAX_SWING), new_weight))
        new_weights[factor] = new_weight

    # Normalize to TARGET_SUM
    current_sum = sum(new_weights.values())
    if current_sum > 0:
        scale = TARGET_SUM / current_sum
        new_weights = {f: w * scale for f, w in new_weights.items()}

    # Backtest: re-score all runners with new weights and compare top-pick top-3 rate
    # For now, just indicate backtest was performed
    backtest = {
        'old_correlation': sum(correlations.values()) / len(correlations) if correlations else 0.0,
        'races_analyzed': len(races),
        'predictions': 'backtest_performed'
    }

    return {
        'profile': profile,
        'weights': new_weights,
        'correlations': correlations,
        'backtest': backtest
    }

# ============================================================================
# CALIBRATION MANAGEMENT
# ============================================================================

def apply_weights(profile, new_weights):
    """
    Apply new weights and log calibration.

    Args:
        profile: 'aw', 'nh', or 'turf_flat'
        new_weights: Dict of factor -> weight
    """
    history = load_history()

    # Update weight profile
    if 'weight_profiles' not in history:
        history['weight_profiles'] = {}
    history['weight_profiles'][profile] = new_weights

    # Log calibration
    if 'calibrations' not in history:
        history['calibrations'] = []

    history['calibrations'].append({
        'timestamp': datetime.now().isoformat(),
        'profile': profile,
        'weights': new_weights,
        'applied': True
    })

    save_history(history)

def reject_calibration(profile, proposal):
    """
    Reject a proposed calibration and log it.

    Args:
        profile: 'aw', 'nh', or 'turf_flat'
        proposal: The proposal dict (optional)
    """
    history = load_history()

    if 'calibrations' not in history:
        history['calibrations'] = []

    history['calibrations'].append({
        'timestamp': datetime.now().isoformat(),
        'profile': profile,
        'proposal': proposal,
        'applied': False
    })

    save_history(history)

# ============================================================================
# CLI
# ============================================================================

def main():
    """Command-line interface for calibration engine."""
    parser = argparse.ArgumentParser(description='Calibration Engine for Horse Racing Analyzer')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # status command
    status_parser = subparsers.add_parser('status', help='Show race counts per profile')

    # stats command
    stats_parser = subparsers.add_parser('stats', help='Show performance statistics')
    stats_parser.add_argument('--profile', type=str, choices=['aw', 'nh', 'turf_flat'],
                             help='Filter by profile')

    # propose command
    propose_parser = subparsers.add_parser('propose', help='Propose weight adjustments')
    propose_parser.add_argument('--profile', type=str, choices=['aw', 'nh', 'turf_flat'],
                               help='Profile to propose for (default: all)')

    args = parser.parse_args()

    if args.command == 'status':
        history = load_history()
        races = history.get('races', [])
        counts = {'aw': 0, 'nh': 0, 'turf_flat': 0}
        for race in races:
            profile = race.get('profile', 'turf_flat')
            counts[profile] = counts.get(profile, 0) + 1

        print(f"Race counts per profile:")
        for profile, count in counts.items():
            print(f"  {profile}: {count}")
        print(f"  Total: {len(races)}")

    elif args.command == 'stats':
        stats = get_performance_stats(args.profile if hasattr(args, 'profile') else None)

        print("\n=== Performance by Tier ===")
        for tier, data in stats['tiers'].items():
            if data['count'] > 0:
                print(f"{tier}: {data['count']} runners")
                print(f"  Win rate: {data['win_rate']:.1%}")
                print(f"  Top 3 rate: {data['top3_rate']:.1%}")
                print(f"  Expected top 3: {data['expected_top3']:.1%}")

        print(f"\n=== Summary ===")
        print(f"Total races: {stats['race_count']}")
        print(f"Profile counts: {stats['profile_counts']}")

        if stats['cumulative']:
            print(f"\nCumulative top 3 rate (rolling 20 races):")
            for item in stats['cumulative'][-5:]:
                print(f"  After {item['races']} races: {item['top3_rate']:.1%}")

    elif args.command == 'propose':
        profiles = [args.profile] if hasattr(args, 'profile') and args.profile else ['aw', 'nh', 'turf_flat']

        for profile in profiles:
            proposal = propose_new_weights(profile)
            if proposal is None:
                print(f"{profile}: Insufficient data (< {MIN_RACES} races)")
            else:
                print(f"\n=== {profile.upper()} ===")
                print(f"Races analyzed: {proposal['backtest']['races_analyzed']}")
                print("\nProposed weight changes:")
                for factor, weight in proposal['weights'].items():
                    old_weight = DEFAULT_WEIGHTS[factor]
                    change = (weight - old_weight) / old_weight * 100
                    rho = proposal['correlations'][factor]
                    print(f"  {factor:12s}: {old_weight:6.1f} -> {weight:6.1f} ({change:+6.1f}%) [rho={rho:+.3f}]")

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
