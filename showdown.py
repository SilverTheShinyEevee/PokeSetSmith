#!/usr/bin/env python3
"""
generate_showdown_set.py
Single-file Pokémon Showdown set generator with:
- EV/IV reverse calculation from observed stats
- Autocorrect (prompt/silent/off) for game-relevant fields
- Ribbons system with online-first ribbons.json creation and list command
- Persisted settings.json and in-script settings menu
- OT + Trainer ID capture
"""

from __future__ import annotations
import os
import sys
import json
import math
import time
import difflib
from typing import Dict, List, Optional, Tuple

# try to import requests; script will handle if missing
try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

# ---------- Defaults and constants ----------
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")
RIBBONS_PATH = os.path.join(SCRIPT_DIR, "ribbons.json")

# Default remote ribbons URL (placeholder). Replace with your own hosted JSON if desired.
DEFAULT_RIBBON_URL = "https://raw.githubusercontent.com/SilverTheShinyEevee/PokeSetSmith/main/ribbons.json"
# Showdown data endpoints (for base stats, moves, abilities, items)
SHOWDOWN_POKEDEX_URL = "https://play.pokemonshowdown.com/data/pokedex.json"
SHOWDOWN_MOVES_URL = "https://play.pokemonshowdown.com/data/moves.json"
SHOWDOWN_ABILITIES_URL = "https://play.pokemonshowdown.com/data/abilities.json"
SHOWDOWN_ITEMS_URL = "https://play.pokemonshowdown.com/data/items.json"

# Basic fallback lists for offline mode (minimal)
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
# Small built-in ribbon dataset for fallback if ribbons.json download fails.
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

# Nature effects mapping - (increased_stat, decreased_stat)
NATURE_EFFECTS = {
    "Lonely":  ("atk","def"), "Brave":   ("atk","spe"), "Adamant": ("atk","spa"), "Naughty": ("atk","spd"),
    "Bold":    ("def","atk"), "Relaxed": ("def","spe"), "Impish":  ("def","spa"), "Lax":     ("def","spd"),
    "Modest":  ("spa","atk"), "Mild":    ("spa","def"), "Quiet":   ("spa","spe"), "Rash":    ("spa","spd"),
    "Calm":    ("spd","atk"), "Gentle":  ("spd","def"), "Sassy":   ("spd","spe"), "Careful": ("spd","spa"),
    "Timid":   ("spe","atk"), "Hasty":   ("spe","def"), "Jolly":   ("spe","spa"), "Naive":   ("spe","spd")
}
# Map stat keys to display/order
STAT_KEYS = ['hp','atk','def','spa','spd','spe']
STAT_DISPLAY = {'hp':'HP','atk':'Atk','def':'Def','spa':'SpA','spd':'SpD','spe':'Spe'}

# ---------- Utility functions ----------
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
    # Minimal normalization: trim and capitalize common words; keep special chars intact
    return s.strip().replace("_"," ").title()

# ---------- Settings management ----------
DEFAULT_SETTINGS = {
    "check_for_ribbon_updates_on_startup": True,
    "ribbon_source_url": DEFAULT_RIBBON_URL,
    "autocorrect_mode": "prompt",   # "prompt" | "silent" | "off"
    "default_iv_value": 31,
    "auto_calculate_ivs_from_observed_stats": True,
    "showdown_export_format": "standard",
    "language": "en",
    "include_ribbons_if_none": True,
    "offline_mode": False,
    "immediate_ribbon_reload_on_url_change": True
}

def load_or_create_settings() -> Dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            data = load_json(SETTINGS_PATH)
            # ensure keys exist
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
    except Exception as e:
        return False

def load_ribbons(settings: Dict) -> Dict[str, List[str]]:
    # Priority:
    # 1. Local ribbons.json if present
    # 2. Download if not present and settings allow
    # 3. Built-in fallback
    if os.path.exists(RIBBONS_PATH):
        try:
            data = load_json(RIBBONS_PATH)
            return data
        except Exception as e:
            print("Warning: existing ribbons.json is invalid; falling back to download or built-in.")
    # try download if allowed
    if not settings.get("offline_mode", False) and settings.get("check_for_ribbon_updates_on_startup", True):
        url = settings.get("ribbon_source_url", DEFAULT_RIBBON_URL)
        print("No local ribbons.json found. Attempting to download the latest ribbon list...")
        ok = download_json_to(RIBBONS_PATH, url)
        if ok:
            print("✅ Successfully downloaded ribbons.json from online source.")
            try:
                return load_json(RIBBONS_PATH)
            except Exception as e:
                print("Warning: downloaded ribbons.json is invalid. Using built-in fallback.")
        else:
            print("⚠️ Unable to download ribbons.json — using built-in fallback.")
    else:
        print("Using built-in ribbon list (offline or update-check disabled).")
    return FALLBACK_RIBBONS.copy()

# ---------- Showdown data fetching (pokedex, moves, abilities, items) ----------
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
    # returns pokedex, moves, abilities, items as dicts (may be empty if offline)
    pokedex = {}
    moves = {}
    abilities = {}
    items = {}
    if settings.get("offline_mode", False) or not HAS_REQUESTS:
        return pokedex, moves, abilities, items
    # try to fetch
    pk = fetch_showdown_data(SHOWDOWN_POKEDEX_URL)
    if pk:
        pokedex = pk
    mv = fetch_showdown_data(SHOWDOWN_MOVES_URL)
    if mv:
        moves = mv
    ab = fetch_showdown_data(SHOWDOWN_ABILITIES_URL)
    if ab:
        abilities = ab
    it = fetch_showdown_data(SHOWDOWN_ITEMS_URL)
    if it:
        items = it
    return pokedex, moves, abilities, items

# ---------- Validation & autocorrect ----------
def get_autocorrect_mode(settings: Dict) -> int:
    m = settings.get("autocorrect_mode", "prompt")
    return {"prompt":1, "silent":2, "off":3}.get(m, 1)

def validate_input(user_input: str, valid_list: List[str], autocorrect_mode: int, label: str="Entry") -> str:
    """
    autocorrect_mode: 1 prompt, 2 silent, 3 off
    valid_list: list of canonical names (already title-cased)
    returns chosen string (may be original if no match or user declines)
    """
    if not user_input:
        return user_input
    u = user_input.strip()
    # normalize some obvious forms
    u_norm = u.replace("_"," ").strip()
    # try few normalization attempts
    candidates = [u_norm, title_case_showdown(u_norm)]
    # also try lower-case compare
    low_map = {v.lower():v for v in valid_list}
    if u_norm.lower() in low_map:
        return low_map[u_norm.lower()]
    # exact title-case match
    t = title_case_showdown(u_norm)
    if t in valid_list:
        return t
    # fuzzy
    close = difflib.get_close_matches(t, valid_list, n=3, cutoff=0.65)
    if not close:
        # as last resort, try simple substring matches
        substring_matches = [v for v in valid_list if u_norm.lower() in v.lower()]
        if substring_matches:
            close = substring_matches[:3]
    if not close or autocorrect_mode == 3:
        # no suggestions or autocorrect is off
        if autocorrect_mode == 3:
            # accept as-is
            return u
        return u
    if autocorrect_mode == 2:
        # silent: accept best suggestion
        print(f"[Auto-corrected] {label}: '{u}' -> '{close[0]}'")
        return close[0]
    # prompt mode
    suggestion = close[0]
    ans = input(f"'{u}' not found. Did you mean '{suggestion}'? (y/n): ").strip().lower()
    if ans.startswith("y"):
        return suggestion
    # if user declines, show other suggestions if present
    if len(close) > 1:
        for idx, s in enumerate(close[1:], start=1):
            ans2 = input(f"Use alternative suggestion '{s}'? (y/n): ").strip().lower()
            if ans2.startswith("y"):
                return s
    # otherwise accept as-is
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
    """
    Brute-force search for (iv, ev) pair such that calc_stat(...) == observed.
    Returns the solution with highest IV and lowest EV if multiple. EV increments of 4.
    """
    solutions = []
    for iv in range(0, max_iv+1):
        # quick estimate range of EV to narrow search:
        # EV range 0-252 stepping by 4; test all if necessary
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
    # Reduce EVs from highest to lowest until total <= 510.
    # We reduce in chunks of 4 (valid EV increments).
    ev_list = list(evs.items())
    # Sort by EV descending, prefer to reduce stats with >0 EV
    while total > 510:
        # find stat with max ev > 0
        stat_to_reduce = None
        max_ev = 0
        for s, v in ev_list:
            if v > max_ev:
                max_ev = v
                stat_to_reduce = s
        if stat_to_reduce is None or max_ev <= 0:
            break
        # reduce by 4
        evs[stat_to_reduce] = max(0, evs[stat_to_reduce] - 4)
        total -= 4
        # refresh ev_list
        ev_list = list(evs.items())
    return evs

# ---------- Interactive settings menu ----------
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
        elif choice == 's':
            save_settings(settings)
            print("Settings saved.")
            return settings
        elif choice == 'x':
            print("Changes cancelled.")
            return settings
        else:
            print("Unknown option.")

# ---------- Main generator ----------
def generate_set(settings: Dict, ribbons: Dict[str,List[str]], pokedex: Dict, moves_db: Dict, abilities_db: Dict, items_db: Dict):
    print("\n=== Pokémon Showdown Set Generator ===\n")
    autocorrect_mode = get_autocorrect_mode(settings)

    # Species: validate with pokedex if available
    species_input = ask("Species (exact or approximate)")
    species = species_input.strip()
    species_validated = species
    species_list = []
    if pokedex:
        species_list = list(pokedex.keys())
    else:
        # if no pokedex data: try nothing, will prompt for manual base stats if needed
        species_list = []

    if species_list:
        species_validated = validate_input(species, [s for s in species_list], autocorrect_mode, label="Species")
        if species_validated not in pokedex and species_validated.lower() in [k.lower() for k in pokedex.keys()]:
            # normalize key
            key = next(k for k in pokedex.keys() if k.lower() == species_validated.lower())
            species_validated = key
    else:
        species_validated = title_case_showdown(species)

    # Attempt to get base stats
    base_stats = None
    if pokedex and species_validated in pokedex:
        # Showdown's pokedex uses 'baseStats' sub-dict
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
            # Last attempt: try to fetch with normalized name fallback
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

    # Basic fields
    nickname = ask("Nickname (leave blank if none)", optional=True)
    shiny = yes_no("Is it shiny?", default=False)
    gender = ask("Gender (M/F/N, leave blank if unknown)", optional=True)
    level_str = ask("Current Level (1-100)", optional=False, default="100")
    try:
        level = int(level_str)
    except:
        level = 100

    ability_input = ask("Ability (optional)", optional=True)
    # validate ability if db exists
    ability = ability_input
    if ability_input and abilities_db:
        ability = validate_input(ability_input, [k for k in abilities_db.keys()], autocorrect_mode, label="Ability")

    # Tera type (SV)
    tera_input = ask("Tera type (SV) (optional)", optional=True)
    tera_type = ""
    if tera_input:
        tera_type = validate_input(tera_input, FALLBACK_TYPES, autocorrect_mode, label="Tera Type")

    # Dynamax/Gigantamax (SwSh)
    dynamax_level = ask("Dynamax Level (SwSh only) (optional)", optional=True)
    gigantamax = False
    cur_game = ask("Current game (optional, used to enable GMax prompt)", optional=True)
    if cur_game and cur_game.strip().lower() in ("sword","shield","sw","sh","sword/shield"):
        gigantamax = yes_no("Has Gigantamax factor?", default=False)

    # Observed stats
    print("\nEnter observed stats you can see in the game (leave blank if unknown). We'll use these to infer EVs/IVs.")
    observed: Dict[str, Optional[int]] = {}
    for k in STAT_KEYS:
        v = ask(f"Observed {STAT_DISPLAY[k]}", optional=True)
        observed[k] = int(v) if v.strip() else None

    # Ask if they want to use observed stats to infer IVs/EVs
    want_infer = False
    if any(v is not None for v in observed.values()):
        default_choice = settings.get("auto_calculate_ivs_from_observed_stats", True)
        want_infer = yes_no("Use observed stats to calculate both IVs and EVs? (If no, IVs will be assumed default)", default=default_choice)
    else:
        want_infer = False

    # Optionally prompt for IVs when the user wants custom IVs instead of inference.
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
                else:
                    ivs_input[k] = settings.get('default_iv_value',31)

    # Now compute IVs and EVs
    ivs: Dict[str,int] = {k: settings.get('default_iv_value',31) for k in STAT_KEYS}
    evs: Dict[str,int] = {k: 0 for k in STAT_KEYS}
    # fill known IVs if user provided
    if not want_infer and custom_ivs_provided:
        ivs.update(ivs_input)

    # For nature multiplier we need a nature input; validate nature
    nature_input = ask("Nature (optional)", optional=True)
    nature = ""
    if nature_input:
        nature = validate_input(nature_input, FALLBACK_NATURES, get_autocorrect_mode(settings), label="Nature")

    # reverse calculation per stat
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
                    # Not solvable: fall back to defaults or manual attempt with default IV
                    print(f"⚠️ Could not find IV/EV pair for {STAT_DISPLAY[s]} that matches observed stat. Defaulting IV to {settings.get('default_iv_value')} and EV 0.")
                    ivs[s] = settings.get('default_iv_value',31)
                    evs[s] = 0
            else:
                # IVs are assumed; back-calc EV only
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

    # Clamp EVs to legal totals
    total_evs = sum(evs.values())
    if total_evs > 510:
        print(f"⚠️ Total EVs {total_evs} exceed 510. Reducing EVs to meet the 510 cap.")
        evs = clamp_ev_distribution(evs)
        total_evs = sum(evs.values())
        print(f"→ New total EVs: {total_evs}")

    # Moves (up to 4) with validation using moves_db if available
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

    # Item validation
    item_raw = ask("Held item (optional)", optional=True)
    item = ""
    item_db_list = list(items_db.keys()) if items_db else []
    if item_raw:
        if item_db_list:
            item = validate_input(item_raw, item_db_list, autocorrect_mode, label="Item")
        else:
            item = title_case_showdown(item_raw)

    # Original Trainer + Trainer ID
    ot = ask("Original Trainer (OT) (optional)", optional=True)
    trainer_id = ""
    if ot:
        trainer_id = ask("Trainer ID (optional but recommended)", optional=True)

    # Moves/ability/item post-processing: ensure capitalization consistent
    # Build Showdown lines
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

    # EVs and IVs formatting: only show EV stats that are >0; IVs only show non-defaults to reduce clutter
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
    else:
        # If user explicitly requested IV output when all default, still show full line with defaults? For now we omit if all default.
        pass

    for mv in moves_list:
        lines.append(f"- {mv}")

    # Metadata comments
    lines.append("")
    lines.append(f"// Original Game: {cur_game if cur_game else 'Unknown'}")
    if ot:
        if trainer_id:
            lines.append(f"// OT: {ot} (ID: {trainer_id})")
        else:
            lines.append(f"// OT: {ot}")
    if any(observed.values()):
        obs_comments = ", ".join([f"{STAT_DISPLAY[k]} {observed[k]}" for k in STAT_KEYS if observed[k] is not None])
        lines.append(f"// Observed stats: {obs_comments}")
    lines.append(f"// EV assumption: IVs assumed {default_iv} where not derived" if not want_infer else f"// IVs/EVs inferred from observed stats")
    # Ribbons entry
    ribbons_entered: List[str] = []
    wants_ribbons = yes_no("\nThis Pokémon may have ribbons or marks from your playthrough. Would you like to add them now?", default=True)
    if wants_ribbons:
        print("Enter ribbon name one at a time. Type 'list' to view known ribbons. Press Enter on blank line to finish.")
        ribbon_names_flat = []
        for cat, items in ribbons.items():
            ribbon_names_flat.extend(items)
        while True:
            rraw = ask("Enter ribbon name (or 'list' to view, Enter to finish)", optional=True)
            if not rraw.strip():
                break
            if rraw.strip().lower() == 'list':
                # print categorized list
                print("\n=== Known Ribbons ===")
                for cat, items in ribbons.items():
                    print(f"\n--- {cat} ---")
                    for it in sorted(items):
                        print(it)
                print("")
                continue
            rr = validate_input(rraw, ribbon_names_flat, get_autocorrect_mode(settings), label="Ribbon")
            # If the validated ribbon isn't in the known list, offer a warning but accept
            if rr not in ribbon_names_flat:
                ans = yes_no(f"'{rr}' not in known ribbons. Accept as custom ribbon?", default=False)
                if not ans:
                    print("Skipping.")
                    continue
            ribbons_entered.append(rr)
            print(f"Added ribbon: {rr}")
    # If none entered and setting to include none
    if not ribbons_entered and settings.get("include_ribbons_if_none", True):
        lines.append("// Ribbons: none")
    elif ribbons_entered:
        lines.append("// Ribbons: " + ", ".join(ribbons_entered))

    # Save file
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
    # load ribbons (and possibly download on boot)
    ribbons = load_ribbons(settings)
    # load Showdown resources (pokedex/moves/abilities/items) if available
    pokedex, moves_db, abilities_db, items_db = load_showdown_resources(settings)
    # Main menu loop
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
