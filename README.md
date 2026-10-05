# Value Vintage Metagame

A Streamlit metagame browser built from public Value Vintage online tournament
results.

The entire dataset can be rebuilt from scratch from the VV website and the
linked public Moxfield decklists.

## Rules

Decks are considered part of the same archetype when they share at least:

**20 mainboard nonland card slots**

Copies count individually:

```python
shared = sum(
    min(deck_a.get(card, 0), deck_b.get(card, 0))
    for card in deck_a.keys() & deck_b.keys()
)
```

All lands are excluded.

Similarity is **not transitive**. Clustering uses complete-linkage, meaning
every pair of decks within a cluster must independently meet the 20-card
threshold.

## App behavior

The top-level metagame page supports:

- Last 30 days
- Last 60 days
- Last 90 days

Each archetype card shows:

- archetype name
- signature card image
- three signature cards
- metagame percentage for the selected period
- number of deck results

Click **View decks** to open the archetype detail view.

The detail view lists the original information from `vv_online_results.csv`
for all deck results in that archetype and selected time period:

- date
- event
- placement
- player
- record
- submitted archetype
- Moxfield decklist
- VV tournament page

## Full data pipeline

One command rebuilds everything:

```bash
python build_data.py --days 90
```

Stages:

```text
vvmtg.com/category/online-tournaments/
            |
            v
data/vv_online_results.csv
            |
            v
Moxfield deck fetch + raw cache
            |
            v
mainboard / nonland normalization
            |
            v
25-slot complete-link clustering
            |
            v
archetype naming + signature cards
            |
            v
app_data/
```

Output:

```text
data/
├── vv_online_results.csv
├── decklists_raw/
├── card_cache.json
├── decks_normalized.json
├── deck_cards.csv
├── deck_fetch_failures.csv
└── clustering/
    ├── clusters.csv
    └── deck_clusters.csv

app_data/
├── archetype_profiles.csv
├── archetype_profiles.json
├── deck_results.csv
└── vv_online_results.csv
```

The `data/` directory is pipeline/debug/cache data. `app_data/` is all the
Streamlit app needs at runtime.

## Install

```bash
python -m pip install -r requirements.txt
```

## Build data

```bash
python build_data.py --days 90
```

Use the cache on ordinary refreshes. If you intentionally want to redownload
all Moxfield JSON:

```bash
python build_data.py --days 90 --refresh-decks
```

If Moxfield returns HTTP 401/403, you can supply a current bearer token
locally:

```bash
export MOXFIELD_BEARER_TOKEN='...'
python build_data.py --days 90
```

Do not commit that token.

## Run Streamlit

```bash
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

Commit these files to GitHub:

```text
app.py
build_data.py
src/
requirements.txt
app_data/
```

For the simplest deployment model, rebuild `app_data/` locally when you want
to refresh the metagame and commit the updated CSV/JSON files.

Later, this can be automated with GitHub Actions if desired.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes on time windows

The pipeline crawls 90 days by default so the app has enough source data for
all three views.

The app computes 30/60/90-day metagame percentages at display time from
`app_data/deck_results.csv`.

Archetype definitions are built once from the complete crawled dataset. This
keeps cluster identity stable when switching time periods.

## Compact UI

The metagame page uses a denser 5-column desktop card grid with:

- one representative card image;
- archetype name;
- compact signature-card line;
- meta percentage and deck count on one row;
- a single drill-down button.

The archetype detail page uses a compact header and a tighter tournament-results table.

## Clickable archetype cards

The entire archetype tile is clickable. Selecting the card opens that
archetype's tournament-result detail view; there is no separate View decks
button.


## Preserved time window on back navigation

Returning from an archetype detail page now preserves the active 30/60/90-day
selection instead of resetting the metagame view.


## Automatic weekly GitHub refresh

The repository includes:

```text
.github/workflows/update-metagame.yml
```

It rebuilds the 90-day dataset every Monday at 6:00 AM America/Chicago,
validates the result, and commits updated generated data back to the repo.

See [DEPLOYMENT.md](DEPLOYMENT.md) for GitHub and Streamlit Community Cloud
setup.
