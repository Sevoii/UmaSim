# Umamusume Simulations

Compare Champions Meeting teams using the [GlobalSim](https://github.com/Sevoii/GlobalSim) race simulator. The scripts can fetch opponent teams from UmaLogs, convert a captured race into a team file, run a single race, and compare two teams over repeated races.

## Installation

You need Python 3.9 or newer, Git, and a Rust toolchain with Cargo, a native linker, and a C compiler to build GlobalSim. On Windows, install the C++ build tools as well as Rust. Install Rust from [rustup](https://rustup.rs/).

From the root of this repository, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux, use `source .venv/bin/activate` instead. Then install the dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install requests
python -m pip install git+https://github.com/Sevoii/GlobalSim.git
```

GlobalSim is built from source during installation. If you already have a compatible GlobalSim checkout, you can install it with `python -m pip install /path/to/GlobalSim` instead. The scripts depend on its Python bindings; API changes in GlobalSim may require a compatible revision.

## Compare teams

Run commands below from the repository root. A team file contains either an object with an `id` and a `members` array, or an array of three GlobalSim runner objects. For example, extract two teams from the included opponent pool:

```sh
python -c "import json; from pathlib import Path; t=json.loads(Path('data/cm21_teams.json').read_text(encoding='utf-8')); Path('team_a.json').write_text(json.dumps(t[0], indent=2), encoding='utf-8'); Path('team_b.json').write_text(json.dumps(t[1], indent=2), encoding='utf-8')"
python src/compare_teams.py 21 data/cm21_teams.json team_a.json team_b.json --trials 1000 --rng-seed 1
```

The meeting can also be given as `cm21` or the GlobalSim preset `CAPRICORN_CUP_2`. Each trial races both teams against the same two randomly selected opponents with the same seed and gate assignments. Teams with either tested ID are excluded from the opponent pool; at least two other teams must remain. The output includes team win rates, average runner gaps, and the paired win-rate difference. `--rng-seed` makes trial generation reproducible; `--confidence` sets the confidence level, and `--trials` defaults to 100. Use more trials for a more precise estimate. Results describe the supplied opponent pool and simulator, and the normal-approximation interval for the paired difference can be unreliable with few trials or rare differences.

## Other commands

Run one Capricorn Cup 2 race using the first three teams in the pool:

```sh
python src/run_race.py --teams data/cm21_teams.json --seed 1
```

Fetch teams from the latest UmaLogs snapshot for a Champions Meeting (requires network access):

```sh
python src/scrape_umalogs.py 21 --limit 100
python src/scrape_umalogs.py "Capricorn Cup 2" --limit 100
```

The scraper accepts a number, an ID such as `cm21`, or a cup name such as `CAPRICORN_CUP_2`. Use `--offset 100 --limit 100` to skip the first 100 ranked teams and fetch up to the next 100. It writes `data/cm21_teams.json` for these examples, replacing an existing file with that name even when an offset is specified. Use `--out data/other_teams.json` to choose a different output file or `--snapshot ID` to select a specific snapshot. If a meeting has multiple UmaLogs variants, specify the variant ID, such as `cm16-post`.

Convert a captured race JSON into a team file for comparison:

```sh
python src/convert_race.py path/to/race.json --out data/my_team.json
```

This selects the player's team by default. Use `--team-id` to select another team and `--id` to set the output team's ID. See each script's `--help` for its options.
