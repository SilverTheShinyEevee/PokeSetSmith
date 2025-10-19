# PokeSetSmith

**PokeSetSmith** is a Python-based command-line tool that lets you generate accurate **Pokémon Showdown sets** directly from your **in-game caught Pokémon**.

Unlike most set builders, this tool:
- 🧮 Calculates EVs and IVs from **observed stats** *(with 31 IV fallback)*
- 🧠 Validates moves and autocorrects names using Smogon/Showdown data  
- 🏅 Fetches the latest **Ribbon & Mark data** from [Serebii.net](https://www.serebii.net)  
- ⚙️ Saves user preferences in a `settings.json` file  
- 🐍 Runs entirely locally — no account required.

---

## 📁 Project Structure

PKMN-SetForge/
│
├── showdown.py    # Main script
├── scraper.py          # Ribbon scraper (Serebii)
├── ribbons.json               # Generated ribbon list (auto-updated)
├── settings.json              # User settings (auto-generated on first run)
└── README.md                  # This file

---

## 🚀 Features

- 🎯 **Stat-to-EV/IV Conversion** — enter observed stats and get Showdown-accurate spreads.  
- 🧠 **Move Validation** — automatically matches your move names to official Showdown entries.  
- 🪄 **Ribbon System** — live ribbon list updates from Serebii or local fallback.  
- ⚙️ **Settings Menu** — change autocorrect mode, update URLs, toggle offline mode, etc.  
- 🐾 **Game-Specific Fields** — including Tera Type (SV), Dynamax/Gigantamax (SwSh), and more.  
- 🆔 **Trainer Info** — add OT and Trainer ID if desired.

---

## 📦 Requirements

- Python 3.8+
- requests
- beautifulsoup4 (for scraping)
  
Install them with:
pip install -r requirements.txt

---

## 🧰 Usage

### 1. **Run the main tool**

python3 showdown.py

### 2. **Settings menu**

Type 2 at the main menu to configure:

* Ribbon update behavior
* Autocorrect mode
* Default IVs
* Language and format options

### 3. **Export**

When finished, the tool outputs a Showdown-ready set:

// OT: The Lone H (ID: 648155)
// Ribbons: Effort Ribbon, Cloudy Mark

---

## 🪄 Updating Ribbons

The tool checks `ribbon_source_url` on startup and downloads the latest `ribbons.json` if available.
To manually update:

python3 scraper.py

This uses [Serebii.net](https://www.serebii.net/games/ribbons.shtml) as a source.

---

## 📜 License

This project is **not affiliated with Nintendo, Game Freak, or The Pokémon Company**.
Pokémon and related names are trademarks of Nintendo and The Pokémon Company.
This tool is provided for **educational and fan-use only** under [Fair Use](https://en.wikipedia.org/wiki/Fair_use).

Licensed under the MIT License.
See `LICENSE` for details.

---

## 💡 Future Ideas

* 🪙 Optional GUI wrapper
* 🧪 Pokémon HOME compatibility
* 📡 Automatic Smogon import/export
* 🐢 PKHeX-friendly format export

---

✨ **Made with love by fans for fans.**
*“Forge your in-game Pokémon into competitive legends.”*
