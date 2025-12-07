#!/usr/bin/env python3
"""
generate_showdown_set.py
Single-file Pokémon Showdown set generator (updated).
Includes:
- EV/IV reverse calculation from observed stats
- Autocorrect (prompt/silent/off)
- Ribbons system with online-first ribbons.json creation and list command
- Persisted settings.json and in-script settings menu
- OT + Trainer ID capture
- Safe hashed profanity filter (no visible slurs)
- Transferable-game list and generation-specific fields (contest, affection, friendship, memories, marks)
"""

from __future__ import annotations
import os
import sys
import json
import math
import time
import difflib
import hashlib
import re
from typing import Dict, List, Optional, Tuple

# network lib
try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

# ---------- Paths & URLs ----------
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")
RIBBONS_PATH = os.path.join(SCRIPT_DIR, "ribbons.json")

DEFAULT_RIBBON_URL = "https://raw.githubusercontent.com/SilverTheShinyEevee/PokeSetSmith/main/ribbons.json"
SHOWDOWN_POKEDEX_URL = "https://play.pokemonshowdown.com/data/pokedex.json"
SHOWDOWN_MOVES_URL = "https://play.pokemonshowdown.com/data/moves.json"
SHOWDOWN_ABILITIES_URL = "https://play.pokemonshowdown.com/data/abilities.json"
SHOWDOWN_ITEMS_URL = "https://play.pokemonshowdown.com/data/items.json"

# ---------- Fallback lists ----------
FALLBACK_NATURES = [
    "Hardy","Lonely","Brave","Adamant","Naughty",
    "Bold","Docile","Relaxed","Impish","Lax",
    "Timid","Hasty","Serious","Jolly","Naive",
    "Modest","Mild","Quiet","Rash","Calm",
    "Gentle","Sassy","Careful","Quirky","Bashful"
]
FALLBACK_TYPES = [
    "Normal","Fire","Water","Electric","Grass","Ice","Fighting","Poison",
    "Ground","Flying","Psychic","Bug","Rock","Ghost","Dragon","Dark",
    "Steel","Fairy"
]
FALLBACK_RIBBONS = {
    "Common Ribbons": [
        "Effort Ribbon", "Champion Ribbon", "Classic Ribbon", "Best Friends Ribbon"
    ],
    "Marks (Galar / Paldea)": [
        "Curry Mark", "Cloudy Mark", "Stormy Mark", "Rainy Mark", "Jumbo Mark", "Teeny Mark"
    ],
    "Event & Contest Ribbons": [
        "Contest Star Ribbon", "Artist Ribbon", "World Ribbon", "Festival Ribbon"
    ]
}

# ---------- Nature effects ----------
NATURE_EFFECTS = {
    "Lonely":  ("atk","def"), "Brave":   ("atk","spe"), "Adamant": ("atk","spa"), "Naughty": ("atk","spd"),
    "Bold":    ("def","atk"), "Relaxed": ("def","spe"), "Impish":  ("def","spa"), "Lax":     ("def","spd"),
    "Modest":  ("spa","atk"), "Mild":    ("spa","def"), "Quiet":   ("spa","spe"), "Rash":    ("spa","spd"),
    "Calm":    ("spd","atk"), "Gentle":  ("spd","def"), "Sassy":   ("spd","spe"), "Careful": ("spd","spa"),
    "Timid":   ("spe","atk"), "Hasty":   ("spe","def"), "Jolly":   ("spe","spa"), "Naive":   ("spe","spd")
}
STAT_KEYS = ['hp','atk','def','spa','spd','spe']
STAT_DISPLAY = {'hp':'HP','atk':'Atk','def':'Def','spa':'SpA','spd':'SpD','spe':'Spe'}

# ---------- Profanity filter (hashed; no plain slurs) ----------
# NOTE: replace/add with your project's approved SHA256 hashes of normalized tokens.
BLOCKED_HASHES = {
    # placeholder hashes (irreversible) - you may replace with your approved list
    "a13ef31f76b6f3e24b5e23573fdf017d4b07b3a7c55691ed13a532b523b5e94d",
    "c389f163c22e2ad2e8a9f4bfa617f6c60dbb2df1b89de1eb65f6e3f52925cb2f",
    "ff457bccfc76d1c2f9a28398e4a77b7e945f5d2d3b8aeb68f39a1ef1db4cfb41",
}

def normalize_text_for_filter(text: str) -> str:
    leet_map = str.maketrans({
        '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't',
        '@': 'a', '$': 's', '!': 'i'
    })
    text = text.lower().translate(leet_map)
    text = re.sub(r'[^a-z]', '', text)
    return text

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def is_profane(text: str) -> bool:
    if not text or not text.strip():
        return False
    norm = normalize_text_for_filter(text)
    if not norm:
        return False
    return text_hash(norm) in BLOCKED_HASHES

def safe_ask(prompt: str, optional: bool=False, default: Optional[str]=None, settings: Optional[Dict]=None) -> str:
    while True:
        val = ask(prompt, optional=optional, default=default)
        if val == "" and optional:
            return ""
        if settings and settings.get("use_profanity_filter", True):
            if is_profane(val):
                print("⚠️ That value contains disallowed language — please choose another.")
                continue
        return val

# ---------- Utility I/O ----------
def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        json_string = f.read()
        return json.loads(json_string)

def ask(prompt: str, optional: bool=False, default: Optional[str]=None) -> str:
    t = f"{prompt}{' (optional)' if optional else ''}"
    if default is not None:
        t += f" [{default}]"
    t += ": "
    ans = input(t).strip()
    if ans == "" and default is not None:
        return default
    return ans

def yes_no(prompt: str, default: Optional[bool]=None) -> bool:
    suffix = ""
    if default is True:
        suffix = " [Y/n]"
    elif default is False:
        suffix = " [y/N]"
    ans = input(f"{prompt}{suffix}: ").strip().lower()
    if ans == "" and default is not None:
        return default
    return ans.startswith("y")

def title_case_showdown(s: str) -> str:
    return s.strip().replace("_"," ").title()

# ---------- Settings ----------
DEFAULT_SETTINGS = {
    "check_for_ribbon_updates_on_startup": True,
    "ribbon_source_url": DEFAULT_RIBBON_URL,
    "autocorrect_mode": "prompt",
    "default_iv_value": 31,
    "auto_calculate_ivs_from_observed_stats": True,
    "showdown_export_format": "standard",
    "language": "en",
    "include_ribbons_if_none": True,
    "offline_mode": False,
    "immediate_ribbon_reload_on_url_change": True,
    "use_profanity_filter": True
}

def load_or_create_settings() -> Dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            data = load_json(SETTINGS_PATH)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            print("Warning: settings.json exists but couldn't be read. Recreating defaults.")
    save_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)

def save_settings(settings: Dict):
    save_json(SETTINGS_PATH, settings)

# ---------- Ribbon management ----------
def download_json_to(path: str, url: str, timeout: int=8) -> bool:
    if not HAS_REQUESTS:
        return False
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            save_json(path, data)
            return True
        else:
            return False
    except Exception:
        return False

def load_ribbons(settings: Dict) -> Dict[str, List[str]]:
    if os.path.exists(RIBBONS_PATH):
        try:
            data = load_json(RIBBONS_PATH)
            return data
        except Exception:
            print("Warning: existing ribbons.json is invalid; falling back to download or built-in.")
    if not settings.get("offline_mode", False) and settings.get("check_for_ribbon_updates_on_startup", True):
        url = settings.get("ribbon_source_url", DEFAULT_RIBBON_URL)
        print("No local ribbons.json found. Attempting to download the latest ribbon list...")
        ok = download_json_to(RIBBONS_PATH, url)
        if ok:
            print("✅ Successfully downloaded ribbons.json from online source.")
            try:
                return load_json(RIBBONS_PATH)
            except Exception:
                print("Warning: downloaded ribbons.json is invalid. Using built-in fallback.")
        else:
            print("⚠️ Unable to download ribbons.json — using built-in fallback.")
    else:
        print("Using built-in ribbon list (offline or update-check disabled).")
    return FALLBACK_RIBBONS.copy()

# ---------- Showdown data fetching ----------
def fetch_showdown_data(url: str) -> Optional[Dict]:
    if not HAS_REQUESTS:
        return None
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def load_showdown_resources(settings: Dict) -> Tuple[Dict, Dict, Dict, Dict]:
    pokedex = {}
    moves = {}
    abilities = {}
    items = {}
    if settings.get("offline_mode", False) or not HAS_REQUESTS:
        return pokedex, moves, abilities, items
    pk = fetch_showdown_data(SHOWDOWN_POKEDEX_URL)
    if pk: pokedex = pk
    mv = fetch_showdown_data(SHOWDOWN_MOVES_URL)
    if mv: moves = mv
    ab = fetch_showdown_data(SHOWDOWN_ABILITIES_URL)
    if ab: abilities = ab
    it = fetch_showdown_data(SHOWDOWN_ITEMS_URL)
    if it: items = it
    return pokedex, moves, abilities, items

# ---------- Validation & autocorrect ----------
def get_autocorrect_mode(settings: Dict) -> int:
    m = settings.get("autocorrect_mode", "prompt")
    return {"prompt":1, "silent":2, "off":3}.get(m, 1)

def validate_input(user_input: str, valid_list: List[str], autocorrect_mode: int, label: str="Entry") -> str:
    if not user_input:
        return user_input
    u = user_input.strip()
    u_norm = u.replace("_"," ").strip()
    candidates = [u_norm, title_case_showdown(u_norm)]
    low_map = {v.lower():v for v in valid_list}
    if u_norm.lower() in low_map:
        return low_map[u_norm.lower()]
    t = title_case_showdown(u_norm)
    if t in valid_list:
        return t
    close = difflib.get_close_matches(t, valid_list, n=3, cutoff=0.65)
    if not close:
        substring_matches = [v for v in valid_list if u_norm.lower() in v.lower()]
        if substring_matches:
            close = substring_matches[:3]
    if not close or autocorrect_mode == 3:
        if autocorrect_mode == 3:
            return u
        return u
    if autocorrect_mode == 2:
        print(f"[Auto-corrected] {label}: '{u}' -> '{close[0]}'")
        return close[0]
    suggestion = close[0]
    ans = input(f"'{u}' not found. Did you mean '{suggestion}'? (y/n): ").strip().lower()
    if ans.startswith("y"):
        return suggestion
    if len(close) > 1:
        for idx, s in enumerate(close[1:], start=1):
            ans2 = input(f"Use alternative suggestion '{s}'? (y/n): ").strip().lower()
            if ans2.startswith("y"):
                return s
    return u

# ---------- Stat math and reverse calculation ----------
def calc_stat(base: int, iv: int, ev: int, level: int, nature_mult: float, is_hp: bool) -> int:
    if is_hp:
        return math.floor(((2 * base + iv + (ev // 4)) * level) / 100) + level + 10
    else:
        inner = math.floor(((2 * base + iv + (ev // 4)) * level) / 100) + 5
        return math.floor(inner * nature_mult + 1e-9)

def get_nature_multiplier(nature: Optional[str], stat_key: str) -> float:
    if not nature:
        return 1.0
    incdec = NATURE_EFFECTS.get(nature)
    if not incdec:
        return 1.0
    inc, dec = incdec
    if stat_key == inc:
        return 1.1
    if stat_key == dec:
        return 0.9
    return 1.0

def reverse_calc_iv_ev_for_stat(observed: int, base: int, level: int, nature_mult: float, is_hp: bool, max_iv: int=31) -> Optional[Tuple[int,int]]:
    solutions = []
    for iv in range(0, max_iv+1):
        for ev in range(0, 253, 4):
            s = calc_stat(base, iv, ev, level, nature_mult, is_hp)
            if s == observed:
                solutions.append((iv, ev))
    if not solutions:
        return None
    solutions.sort(key=lambda x: (-x[0], x[1]))
    return solutions[0]

def clamp_ev_distribution(evs: Dict[str,int]) -> Dict[str,int]:
    total = sum(evs.values())
    if total <= 510:
        return evs
    while total > 510:
        stat_to_reduce = max(evs.items(), key=lambda x: x[1])[0]
        if evs[stat_to_reduce] <= 0:
            break
        evs[stat_to_reduce] = max(0, evs[stat_to_reduce] - 4)
        total -= 4
    return evs

# ---------- Transferable games list & generation detection ----------
TRANSFERABLE_GAMES = [
    # Gen 1 (3DS VC)
    "red", "green", "blue", "yellow",
    # Gen 2 (3DS VC)
    "gold", "silver", "crystal",
    # Gen 3
    "ruby", "sapphire", "emerald",
    "firered", "leafgreen",
    "colosseum", "xd: gale of darkness", "colosseum bonus disc (us)", "colosseum bonus disc (jp)",
    "pokémon box: ruby & sapphire", "pokemon box: ruby & sapphire",
    # Gen 4
    "diamond", "pearl", "platinum",
    "heartgold", "soulsilver", "battle revolution",
    # Gen 5
    "black", "white", "black 2", "white 2",
    # Gen 6
    "x", "y", "omega ruby", "alpha sapphire",
    # Gen 7
    "sun", "moon", "ultra sun", "ultra moon", "lets go: pikachu", "lets go: eevee", "let's go pikachu", "let's go eevee",
    # Gen 8
    "sword", "shield", "legends: arceus",
    # Gen 9
    "scarlet", "violet", "legends: z-a",
    # Hubs and services
    "pokémon bank", "pokemon bank", "pokémon home", "pokemon home",
    # NSO re-releases
    "colosseum (nso)", "xd: gale of darkness (nso)"
]

# mapping to generation number (best-effort)
GAME_TO_GEN = {
    # gen1 vc
    "red":1,"green":1,"blue":1,"yellow":1,
    # gen2 vc
    "gold":2,"silver":2,"crystal":2,
    # gen3
    "ruby":3,"sapphire":3,"emerald":3,"firered":3,"leafgreen":3,"pokémon box: ruby & sapphire":3,
    "pokemon box: ruby & sapphire":3,
    "colosseum":3,"xd: gale of darkness":3,
    # gen4
    "diamond":4,"pearl":4,"platinum":4,"heartgold":4,"soulsilver":4,"battle revolution":4,
    # gen5
    "black":5,"white":5,"black 2":5,"white 2":5,
    # gen6
    "x":6,"y":6,"omega ruby":6,"alpha sapphire":6,
    # gen7
    "sun":7,"moon":7,"ultra sun":7,"ultra moon":7,"lets go: pikachu":7,"lets go: eevee":7,"let's go pikachu":7,"let's go eevee":7,
    # gen8
    "sword":8,"shield":8,"legends: arceus":8,
    # gen9
    "scarlet":9,"violet":9,"legends: z-a":9
}

def get_generation_from_game(title: str) -> Optional[int]:
    key = title.strip().lower()
    # direct match
    if key in GAME_TO_GEN:
        return GAME_TO_GEN[key]
    # try substring matches
    for k, g in GAME_TO_GEN.items():
        if k in key:
            return g
    return None

def validate_original_game(title: str) -> bool:
    return title.strip().lower() in TRANSFERABLE_GAMES or any(k in title.strip().lower() for k in TRANSFERABLE_GAMES)

# ---------- Interactive settings menu (extended) ----------
def settings_menu(settings: Dict, ribbons: Dict[str,List[str]]) -> Dict:
    while True:
        print("\n=== Settings ===")
        print(f"1. Check for ribbon updates on startup: [{'✅' if settings.get('check_for_ribbon_updates_on_startup') else '❌'}]")
        print(f"2. Ribbon source URL: {settings.get('ribbon_source_url')}")
        print(f"3. Autocorrect mode: [{settings.get('autocorrect_mode')}]")
        print(f"4. Default IV value: {settings.get('default_iv_value')}")
        print(f"5. Auto-calculate IVs/EVs from observed stats: [{'✅' if settings.get('auto_calculate_ivs_from_observed_stats') else '❌'}]")
        print(f"6. Include 'Ribbons: none' in exports: [{'✅' if settings.get('include_ribbons_if_none') else '❌'}]")
        print(f"7. Offline mode: [{'✅' if settings.get('offline_mode') else '❌'}]")
        print(f"8. Immediate ribbon reload on URL change: [{'✅' if settings.get('immediate_ribbon_reload_on_url_change') else '❌'}]")
        print(f"9. Use profanity filter for free-form fields: [{'✅' if settings.get('use_profanity_filter') else '❌'}]")
        print(f"s. Save and return")
        print(f"x. Cancel and return")
        choice = input("Choose setting to edit (number/s/x): ").strip().lower()
        if choice == '1':
            settings['check_for_ribbon_updates_on_startup'] = not settings.get('check_for_ribbon_updates_on_startup', True)
            print("Toggled.")
        elif choice == '2':
            new = input("Enter new ribbon source URL (or Enter to cancel): ").strip()
            if new:
                settings['ribbon_source_url'] = new
                print("Ribbon source URL updated.")
                if settings.get('immediate_ribbon_reload_on_url_change', True):
                    print("Attempting immediate reload of ribbons from new URL...")
                    ok = download_json_to(RIBBONS_PATH, new)
                    if ok:
                        print("✅ Ribbons reloaded.")
                        ribbons.clear()
                        ribbons.update(load_json(RIBBONS_PATH))
                    else:
                        print("⚠️ Failed to download from new URL. No change to ribbons.")
        elif choice == '3':
            cur = settings.get('autocorrect_mode','prompt')
            cycle = {'prompt':'silent','silent':'off','off':'prompt'}
            settings['autocorrect_mode'] = cycle.get(cur,'prompt')
            print(f"Autocorrect mode set to {settings['autocorrect_mode']}.")
        elif choice == '4':
            val = input(f"Enter default IV value (0-31) [{settings.get('default_iv_value')}]: ").strip()
            if val:
                try:
                    vi = int(val)
                    if 0 <= vi <= 31:
                        settings['default_iv_value'] = vi
                        print("Default IV updated.")
                    else:
                        print("Invalid number.")
                except:
                    print("Invalid input.")
        elif choice == '5':
            settings['auto_calculate_ivs_from_observed_stats'] = not settings.get('auto_calculate_ivs_from_observed_stats', True)
            print("Toggled.")
        elif choice == '6':
            settings['include_ribbons_if_none'] = not settings.get('include_ribbons_if_none', True)
            print("Toggled.")
        elif choice == '7':
            settings['offline_mode'] = not settings.get('offline_mode', False)
            print("Toggled.")
        elif choice == '8':
            settings['immediate_ribbon_reload_on_url_change'] = not settings.get('immediate_ribbon_reload_on_url_change', True)
            print("Toggled.")
        elif choice == '9':
            settings['use_profanity_filter'] = not settings.get('use_profanity_filter', True)
            print("Toggled.")
        elif choice == 's':
            save_settings(settings)
            print("Settings saved.")
            return settings
        elif choice == 'x':
            print("Changes cancelled.")
            return settings
        else:
            print("Unknown option.")

# ---------- Main generator (enhanced prompts per generation) ----------
def generate_set(settings: Dict, ribbons: Dict[str,List[str]], pokedex: Dict, moves_db: Dict, abilities_db: Dict, items_db: Dict):
    print("\n=== Pokémon Showdown Set Generator ===\n")
    autocorrect_mode = get_autocorrect_mode(settings)

    # Species
    species_input = ask("Species (exact or approximate)")
    species = species_input.strip()
    species_validated = species
    species_list = list(pokedex.keys()) if pokedex else []
    if species_list:
        species_validated = validate_input(species, [s for s in species_list], autocorrect_mode, label="Species")
        if species_validated not in pokedex and species_validated.lower() in [k.lower() for k in pokedex.keys()]:
            key = next(k for k in pokedex.keys() if k.lower() == species_validated.lower())
            species_validated = key
    else:
        species_validated = title_case_showdown(species)

    # Attempt to get base stats
    base_stats = None
    if pokedex and species_validated in pokedex:
        try:
            bs = pokedex[species_validated].get('baseStats', None)
            if bs:
                base_stats = { 'hp': bs['hp'], 'atk': bs['atk'], 'def': bs['def'], 'spa': bs['spa'], 'spd': bs['spd'], 'spe': bs['spe'] }
        except Exception:
            base_stats = None
    if base_stats is None:
        print("Could not determine base stats automatically.")
        if settings.get("offline_mode", False) or not HAS_REQUESTS:
            print("Please enter base stats manually (HP, Atk, Def, SpA, SpD, Spe).")
            base_stats = {}
            for k in STAT_KEYS:
                while True:
                    v = ask(f"Base {STAT_DISPLAY[k]}", optional=False)
                    try:
                        vi = int(v)
                        base_stats[k] = vi
                        break
                    except:
                        print("Enter an integer.")
        else:
            try:
                pk = fetch_showdown_data(SHOWDOWN_POKEDEX_URL)
                if pk and species_validated in pk:
                    bs = pk[species_validated].get('baseStats', None)
                    if bs:
                        base_stats = { 'hp': bs['hp'], 'atk': bs['atk'], 'def': bs['def'], 'spa': bs['spa'], 'spd': bs['spd'], 'spe': bs['spe'] }
            except:
                base_stats = None
            if base_stats is None:
                print("Please enter base stats manually (HP, Atk, Def, SpA, SpD, Spe).")
                base_stats = {}
                for k in STAT_KEYS:
                    while True:
                        v = ask(f"Base {STAT_DISPLAY[k]}", optional=False)
                        try:
                            vi = int(v)
                            base_stats[k] = vi
                            break
                        except:
                            print("Enter an integer.")

    # Basic fields (use safe_ask for free-form when enabled)
    nickname = safe_ask("Nickname (leave blank if none)", optional=True, settings=settings)
    shiny = yes_no("Is it shiny?", default=False)
    gender = ask("Gender (M/F/N, leave blank if unknown)", optional=True)
    level_str = ask("Current Level (1-100)", optional=False, default="100")
    try:
        level = int(level_str)
    except:
        level = 100

    ability_input = ask("Ability (optional)", optional=True)
    ability = ability_input
    if ability_input and abilities_db:
        ability = validate_input(ability_input, [k for k in abilities_db.keys()], autocorrect_mode, label="Ability")

    tera_input = ask("Tera type (SV) (optional)", optional=True)
    tera_type = ""
    if tera_input:
        tera_type = validate_input(tera_input, FALLBACK_TYPES, autocorrect_mode, label="Tera Type")

    dynamax_level = ask("Dynamax Level (SwSh only) (optional)", optional=True)
    gigantamax = False
    cur_game = safe_ask("Current game (optional, used to enable GMax prompt)", optional=True, settings=settings)
    gen = get_generation_from_game(cur_game) if cur_game else None
    if cur_game and not validate_original_game(cur_game):
        print("⚠️ Note: The original/current game entered is not in the transferable-games list. This may affect legality.")
    if cur_game and gen:
        print(f"Detected generation: {gen}")
    else:
        if cur_game:
            print("Could not detect generation automatically; generation-specific fields will be optional.")

    if cur_game and cur_game.strip().lower() in ("sword","shield","sw","sh","sword/shield"):
        gigantamax = yes_no("Has Gigantamax factor?", default=False)

    # Observed stats
    print("\nEnter observed stats you can see in the game (leave blank if unknown). We'll use these to infer EVs/IVs.")
    observed: Dict[str, Optional[int]] = {}
    for k in STAT_KEYS:
        v = ask(f"Observed {STAT_DISPLAY[k]}", optional=True)
        observed[k] = int(v) if v.strip() else None

    # Infer IVs/EVs?
    want_infer = False
    if any(v is not None for v in observed.values()):
        default_choice = settings.get("auto_calculate_ivs_from_observed_stats", True)
        want_infer = yes_no("Use observed stats to calculate both IVs and EVs? (If no, IVs will be assumed default)", default=default_choice)
    else:
        want_infer = False

    # IV entry if not inferring
    custom_ivs_provided = False
    ivs_input = {}
    if not want_infer:
        use_defaults = yes_no(f"Assume default IVs of {settings.get('default_iv_value',31)} for all stats? (y to accept, n to enter custom IVs)", default=True)
        if use_defaults:
            ivs_input = {k: settings.get('default_iv_value',31) for k in STAT_KEYS}
        else:
            custom_ivs_provided = True
            for k in STAT_KEYS:
                v = ask(f"IV for {STAT_DISPLAY[k]} (0-31) (press Enter for default {settings.get('default_iv_value')} )", optional=True)
                if v.strip():
                    try:
                        vi = int(v)
                        if 0 <= vi <= 31:
                            ivs_input[k] = vi
                        else:
                            print("Invalid - must be 0-31. Using default.")
                            ivs_input[k] = settings.get('default_iv_value',31)
                    except:
                        ivs_input[k] = settings.get('default_iv_value',31)

    # Compute IVs/EVs
    ivs: Dict[str,int] = {k: settings.get('default_iv_value',31) for k in STAT_KEYS}
    evs: Dict[str,int] = {k: 0 for k in STAT_KEYS}
    if not want_infer and custom_ivs_provided:
        ivs.update(ivs_input)

    nature_input = ask("Nature (optional)", optional=True)
    nature = ""
    if nature_input:
        nature = validate_input(nature_input, FALLBACK_NATURES, get_autocorrect_mode(settings), label="Nature")

    if any(observed[k] is not None for k in STAT_KEYS):
        print("\nCalculating IVs/EVs from observed stats...")
        for s in STAT_KEYS:
            obs_val = observed[s]
            if obs_val is None:
                continue
            nm = get_nature_multiplier(nature, s)
            if want_infer:
                sol = reverse_calc_iv_ev_for_stat(obs_val, base_stats[s], level, nm, s=='hp', max_iv=31)
                if sol:
                    iv_calc, ev_calc = sol
                    ivs[s] = iv_calc
                    evs[s] = ev_calc
                    print(f"→ {STAT_DISPLAY[s]}: IV {iv_calc}, EV {ev_calc}")
                else:
                    print(f"⚠️ Could not find IV/EV pair for {STAT_DISPLAY[s]}. Defaulting IV to {settings.get('default_iv_value')} and EV 0.")
                    ivs[s] = settings.get('default_iv_value',31)
                    evs[s] = 0
            else:
                iv_assumed = ivs[s]
                found_ev = None
                for ev in range(0, 253, 4):
                    stat_calc = calc_stat(base_stats[s], iv_assumed, ev, level, nm, s=='hp')
                    if stat_calc == obs_val:
                        found_ev = ev
                        break
                if found_ev is not None:
                    evs[s] = found_ev
                    print(f"→ {STAT_DISPLAY[s]}: IV {iv_assumed}, EV {found_ev}")
                else:
                    print(f"⚠️ Observed {STAT_DISPLAY[s]} couldn't be matched with IV={iv_assumed}. Defaulting EV 0.")
                    evs[s] = 0

    total_evs = sum(evs.values())
    if total_evs > 510:
        print(f"⚠️ Total EVs {total_evs} exceed 510. Reducing EVs to meet the 510 cap.")
        evs = clamp_ev_distribution(evs)
        total_evs = sum(evs.values())
        print(f"→ New total EVs: {total_evs}")

    # Moves
    moves_list = []
    print("\nEnter up to 4 moves (press Enter to skip a slot).")
    move_db_list = list(moves_db.keys()) if moves_db else []
    for i in range(1,5):
        mv_raw = ask(f"Move {i}", optional=True)
        if not mv_raw.strip():
            continue
        if move_db_list:
            mv = validate_input(mv_raw, move_db_list, autocorrect_mode, label="Move")
        else:
            mv = title_case_showdown(mv_raw)
        moves_list.append(mv)

    # Item
    item_raw = ask("Held item (optional)", optional=True)
    item = ""
    item_db_list = list(items_db.keys()) if items_db else []
    if item_raw:
        if item_db_list:
            item = validate_input(item_raw, item_db_list, autocorrect_mode, label="Item")
        else:
            item = title_case_showdown(item_raw)

    # OT + ID
    ot = safe_ask("Original Trainer (OT) (optional)", optional=True, settings=settings)
    trainer_id = ""
    if ot:
        trainer_id = safe_ask("Trainer ID (optional but recommended)", optional=True, settings=settings)

    # Generation-specific extra fields
    contest_vals = {}
    affection_val = None
    memory_val = ""
    friendship_val = None
    marks_entered = []
    ribbons_entered: List[str] = []

    if gen is not None:
        # Friendship (Gen2+)
        if gen >= 2:
            f_in = ask("Friendship (0-255) (optional)", optional=True)
            friendship_val = int(f_in) if f_in.strip().isdigit() else None
        # Contest stats (Gen3-6)
        if 3 <= gen <= 6:
            print("\nEnter Contest stats (0-255). Leave blank to skip.")
            for label in ("Cool","Beauty","Cute","Smart","Tough","Sheen"):
                v = ask(label, optional=True)
                contest_vals[label.lower()] = int(v) if v.strip().isdigit() else None
        # Affection/Memories (Gen6-7)
        if 6 <= gen <= 7:
            a_in = ask("Affection (0-255) (optional)", optional=True)
            affection_val = int(a_in) if a_in.strip().isdigit() else None
            memory_val = safe_ask("Memory (flavor text, optional)", optional=True, settings=settings)
        # Marks (Gen8/9 - Paldea/Galar style)
        if gen >= 8:
            print("\nEnter Marks (type 'list' to view known marks, Enter blank to finish).")
            flat_ribbon_names = []
            for cat, items in ribbons.items():
                flat_ribbon_names.extend(items)
            while True:
                rraw = safe_ask("Enter mark (or 'list' to view)", optional=True, settings=settings)
                if not rraw.strip():
                    break
                if rraw.strip().lower() == "list":
                    print("\n=== Known Marks/Ribbons ===")
                    for cat, items in ribbons.items():
                        print(f"\n--- {cat} ---")
                        for it in sorted(items):
                            print(it)
                    print("")
                    continue
                # basic acceptance / autocorrect
                rr = validate_input(rraw, flat_ribbon_names, get_autocorrect_mode(settings), label="Mark")
                if rr not in flat_ribbon_names:
                    ans = yes_no(f"'{rr}' not in known ribbons/marks. Accept as custom mark?", default=False)
                    if not ans:
                        print("Skipping.")
                        continue
                    if settings.get("use_profanity_filter", True) and is_profane(rr):
                        print("⚠️ That mark name is not allowed due to disallowed language. Skipping.")
                        continue
                marks_entered.append(rr)
    else:
        print("Generation unknown — you can still enter optional generation-specific values manually if desired.")

    # Ribbons general prompt (always allowed)
    wants_ribbons = yes_no("\nWould you like to add ribbons now?", default=True)
    if wants_ribbons:
        flat_ribbon_names = []
        for cat, items in ribbons.items():
            flat_ribbon_names.extend(items)
        print("Enter ribbon name one at a time. Type 'list' to view known ribbons. Press Enter on blank line to finish.")
        while True:
            rraw = safe_ask("Enter ribbon name (or 'list' to view, Enter to finish)", optional=True, settings=settings)
            if not rraw.strip():
                break
            if rraw.strip().lower() == 'list':
                print("\n=== Known Ribbons ===")
                for cat, items in ribbons.items():
                    print(f"\n--- {cat} ---")
                    for it in sorted(items):
                        print(it)
                print("")
                continue
            rr = validate_input(rraw, flat_ribbon_names, get_autocorrect_mode(settings), label="Ribbon")
            if rr not in flat_ribbon_names:
                ans = yes_no(f"'{rr}' not in known ribbons. Accept as custom ribbon?", default=False)
                if not ans:
                    print("Skipping.")
                    continue
                if settings.get("use_profanity_filter", True) and is_profane(rr):
                    print("⚠️ That ribbon name is not allowed due to disallowed language. Skipping.")
                    continue
            ribbons_entered.append(rr)
            print(f"Added ribbon: {rr}")

    # Prepare output lines
    display_name = nickname if nickname else species_validated
    filename_safe = "".join(c for c in display_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    lines: List[str] = []
    header = f"{display_name} ({species_validated})"
    if item:
        header += f" @ {item}"
    lines.append(header)
    if ability:
        lines.append(f"Ability: {ability}")
    lines.append(f"Level: {level}")
    if shiny:
        lines.append("Shiny: Yes")
        # note: all gens support shininess existence; older gens may not display it
        lines.append("// Note: Shininess recorded. (All games support DVs leading to shininess; some titles do not show it visually.)")
    if gender and gender.upper() in ("M","F"):
        lines.append(f"Gender: {gender.upper()}")
    if nature:
        lines.append(f"{nature} Nature")
    if tera_type:
        lines.append(f"Tera Type: {tera_type}")
    if gigantamax:
        lines.append("Gigantamax: Yes")
    if dynamax_level:
        lines.append(f"Dynamax Level: {dynamax_level}")

    # EVs / IVs
    default_iv = settings.get('default_iv_value',31)
    ev_parts = []
    for k in STAT_KEYS:
        if evs.get(k,0) > 0:
            ev_parts.append(f"{evs[k]} {STAT_DISPLAY[k]}")
    if ev_parts:
        lines.append("EVs: " + " / ".join(ev_parts))
    iv_parts = []
    for k in STAT_KEYS:
        if ivs.get(k, default_iv) != default_iv:
            iv_parts.append(f"{ivs[k]} {STAT_DISPLAY[k]}")
    if iv_parts:
        lines.append("IVs: " + " / ".join(iv_parts))

    # Moves
    for mv in moves_list:
        lines.append(f"- {mv}")

    # Metadata
    lines.append("")
    lines.append(f"// Current Game: {cur_game if cur_game else 'Unknown'}")
    if ot:
        if trainer_id:
            lines.append(f"// OT: {ot} (ID: {trainer_id})")
        else:
            lines.append(f"// OT: {ot}")
    if gen:
        lines.append(f"// Detected Generation: {gen}")
    if friendship_val is not None:
        lines.append(f"// Friendship: {friendship_val}")
    if contest_vals:
        contest_str = ", ".join([f"{k.capitalize()} {v}" for k, v in contest_vals.items() if v is not None])
        if contest_str:
            lines.append(f"// Contest: {contest_str}")
    if affection_val is not None:
        lines.append(f"// Affection: {affection_val}")
    if memory_val:
        lines.append(f"// Memory: {memory_val}")
    if marks_entered:
        lines.append(f"// Marks: {', '.join(marks_entered)}")
    if ribbons_entered:
        lines.append(f"// Ribbons: {', '.join(ribbons_entered)}")
    else:
        if settings.get("include_ribbons_if_none", True):
            lines.append("// Ribbons: none")
    if any(observed.values()):
        obs_comments = ", ".join([f"{STAT_DISPLAY[k]} {observed[k]}" for k in STAT_KEYS if observed[k] is not None])
        lines.append(f"// Observed stats: {obs_comments}")
    lines.append(f"// EV assumption: IVs assumed {default_iv} where not derived" if not want_infer else f"// IVs/EVs inferred from observed stats")

    showdown_text = "\n".join(lines)
    filename = f"{filename_safe}_Showdown_Set.txt"
    filepath = os.path.abspath(os.path.join(SCRIPT_DIR, filename))
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(showdown_text)
        print("\n=== Pokémon Showdown Set ===")
        print(showdown_text)
        print(f"\n✅ Set saved as: {filepath}")
    except Exception as e:
        print("Error saving file:", e)
        print("\n=== Pokémon Showdown Set (preview) ===")
        print(showdown_text)

# ---------- Main program flow ----------
def main():
    settings = load_or_create_settings()
    ribbons = load_ribbons(settings)
    pokedex, moves_db, abilities_db, items_db = load_showdown_resources(settings)
    while True:
        print("\n=== Main Menu ===")
        print("1) Generate Pokémon Showdown set")
        print("2) Settings")
        print("3) Update ribbons now")
        print("4) Exit")
        choice = input("Choose an option: ").strip()
        if choice == '1':
            generate_set(settings, ribbons, pokedex, moves_db, abilities_db, items_db)
        elif choice == '2':
            settings = settings_menu(settings, ribbons)
            save_settings(settings)
        elif choice == '3':
            if settings.get("offline_mode", False):
                print("Offline mode is enabled in settings. Unable to update ribbons now.")
            else:
                url = settings.get("ribbon_source_url", DEFAULT_RIBBON_URL)
                print(f"Attempting to download ribbons.json from {url} ...")
                ok = download_json_to(RIBBONS_PATH, url)
                if ok:
                    print("✅ Ribbons updated successfully.")
                    try:
                        ribbons.clear()
                        ribbons.update(load_json(RIBBONS_PATH))
                    except:
                        print("Warning: downloaded ribbons.json invalid.")
                else:
                    print("⚠️ Could not download ribbons.json.")
        elif choice == '4':
            print("Goodbye.")
            return
        else:
            print("Unknown option. Enter 1-4.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
        sys.exit(0)
