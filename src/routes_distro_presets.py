"""
Saved distro presets (persisted to disk, shared across all clients).

A distro preset is what a distro's face is - its system, input, rating per
leg, breaker setting, phasing and output rows - saved under a name so the
next show can start from it (owner ruling, 2026-10-16: "users can SAVE their
own distros as presets"). Kept the way named layouts are: one JSON file
beside the presets folder, so they survive a restart and a new version. The
browser cleans a preset again before it applies one (app-distro-systems.js
_normalizeOutputRows); this end only refuses what could not be one.
"""
import json
import os

from flask import Blueprint, request, jsonify

from app import PRESETS_DIR_PATH, log_event

distro_presets_bp = Blueprint('distro_presets', __name__)

# Beside the presets folder, like layouts. Tests point this at a scratch file.
DISTRO_PRESETS_FILE = os.path.join(os.path.dirname(PRESETS_DIR_PATH),
                                   'distro_presets', 'distro_presets.json')

MAX_PRESETS = 100
MAX_NAME = 60
MAX_ROWS = 40
SYSTEMS = {'120/208', '120/240', '120', '230/400', '230'}
ROW_KEYS = {'id', 'connector', 'count', 'coupling', 'breakerA', 'pairedWith'}


def _clean_name(name):
    if not isinstance(name, str):
        return None
    name = ' '.join(name.split())
    if not name or len(name) > MAX_NAME:
        return None
    return name


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_distro(body):
    if not isinstance(body, dict) or body.get('system') not in SYSTEMS:
        return False
    rows = body.get('rows')
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        return False
    for r in rows:
        if not isinstance(r, dict) or not set(r) <= ROW_KEYS:
            return False
        if not isinstance(r.get('connector'), str) or len(r['connector']) > 20:
            return False
        if not _number(r.get('count')) or not 0 < r['count'] < 100:
            return False
        if r.get('coupling') not in ('ln', 'll'):
            return False
        if 'breakerA' in r and not (_number(r['breakerA']) and 0 < r['breakerA'] < 1000):
            return False
        if r.get('pairedWith') is not None and not isinstance(r['pairedWith'], str):
            return False
    rating = body.get('ratingA')
    if rating is not None and not (_number(rating) and 0 < rating < 10000):
        return False
    return True


def _read():
    try:
        with open(DISTRO_PRESETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get('presets') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [i for i in items
            if isinstance(i, dict) and _clean_name(i.get('name')) and _valid_distro(i.get('distro'))]


def _write(items):
    os.makedirs(os.path.dirname(DISTRO_PRESETS_FILE), exist_ok=True)
    tmp = DISTRO_PRESETS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'presets': items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DISTRO_PRESETS_FILE)


def _sorted(items):
    return sorted(items, key=lambda i: i['name'].lower())


@distro_presets_bp.route('/api/distro-presets', methods=['GET'])
def list_distro_presets():
    return jsonify({'presets': _sorted(_read())})


@distro_presets_bp.route('/api/distro-presets', methods=['PUT'])
def save_distro_preset():
    """Save under a name; a preset already under that name is replaced."""
    data = request.get_json(silent=True) or {}
    name = _clean_name(data.get('name'))
    body = data.get('distro')
    if not name:
        return jsonify({'error': f'a preset needs a name of 1 to {MAX_NAME} characters'}), 400
    if not _valid_distro(body):
        log_event('distro_preset_rejected', {'name': name})
        return jsonify({'error': 'that is not a distro this app can open'}), 400
    items = [i for i in _read() if i['name'].lower() != name.lower()]
    if len(items) >= MAX_PRESETS:
        return jsonify({'error': f'{MAX_PRESETS} presets are saved already - delete one first'}), 400
    items.append({'name': name, 'distro': body})
    _write(items)
    log_event('distro_preset_saved', {'name': name})
    return jsonify({'presets': _sorted(items)})


@distro_presets_bp.route('/api/distro-presets', methods=['DELETE'])
def delete_distro_preset():
    data = request.get_json(silent=True) or {}
    name = _clean_name(data.get('name'))
    items = _read()
    kept = [i for i in items if not name or i['name'].lower() != name.lower()]
    if len(kept) == len(items):
        return jsonify({'error': 'no preset by that name'}), 404
    _write(kept)
    log_event('distro_preset_deleted', {'name': name})
    return jsonify({'presets': _sorted(kept)})
