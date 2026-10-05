from __future__ import annotations

from datetime import timedelta
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DATA_DIR = Path("app_data")

st.set_page_config(
    page_title="Value Vintage Metagame",
    page_icon="🃏",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --vv-border: rgba(128,128,128,.22);
      --vv-muted: rgba(128,128,128,.88);
      --vv-surface: rgba(128,128,128,.06);
    }

    .block-container {
      padding-top: 1.0rem;
      padding-bottom: 2rem;
      max-width: 1380px;
    }

    [data-testid="stSidebar"] > div:first-child {
      padding-top: 1.1rem;
    }

    .vv-header {
      margin-bottom: .35rem;
    }

    .vv-subtitle {
      color: var(--vv-muted);
      font-size: .92rem;
      margin-top: -.15rem;
      margin-bottom: .9rem;
    }

    .vv-card-link {
      display: block;
      box-sizing: border-box;
      border: 1px solid var(--vv-border);
      border-radius: 12px;
      padding: .7rem;
      background: var(--vv-surface);
      height: 100%;
      text-decoration: none !important;
      color: inherit !important;
      transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease;
      cursor: pointer;
    }

    .vv-card-link:hover {
      transform: translateY(-2px);
      border-color: rgba(128,128,128,.42);
      box-shadow: 0 6px 18px rgba(0,0,0,.08);
      text-decoration: none !important;
      color: inherit !important;
    }

    .vv-card-image {
      display: block;
      width: 100%;
      aspect-ratio: 488 / 680;
      object-fit: cover;
      object-position: top center;
      border-radius: 8px;
      margin-bottom: .45rem;
    }

    .vv-card-image-placeholder {
      width: 100%;
      aspect-ratio: 488 / 680;
      border-radius: 8px;
      margin-bottom: .45rem;
      background: rgba(128,128,128,.10);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--vv-muted);
      font-size: .78rem;
    }

    .vv-card-cta {
      margin-top: .45rem;
      font-size: .8rem;
      font-weight: 600;
      color: var(--vv-muted);
    }

    .vv-card-title {
      font-size: 1.05rem;
      line-height: 1.15;
      font-weight: 700;
      margin: .15rem 0 .2rem 0;
    }

    .vv-signature {
      color: var(--vv-muted);
      font-size: .78rem;
      line-height: 1.2;
      min-height: 2.0rem;
      margin-bottom: .45rem;
    }

    .vv-card-stats {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: .65rem;
      margin: .25rem 0 .45rem 0;
    }

    .vv-card-stat-main {
      font-size: 1.15rem;
      font-weight: 750;
    }

    .vv-card-stat-label {
      color: var(--vv-muted);
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .04em;
    }

    .vv-detail-meta {
      display: flex;
      gap: 1.6rem;
      flex-wrap: wrap;
      margin: .35rem 0 .8rem 0;
    }

    .vv-detail-item {
      min-width: 95px;
    }

    .vv-detail-value {
      font-weight: 750;
      font-size: 1.15rem;
    }

    .vv-detail-label {
      color: var(--vv-muted);
      font-size: .73rem;
      text-transform: uppercase;
      letter-spacing: .04em;
    }

    div[data-testid="stImage"] img {
      border-radius: 8px;
      object-fit: cover;
    }

    div[data-testid="stButton"] button {
      border-radius: 8px;
      padding-top: .35rem;
      padding-bottom: .35rem;
      font-size: .86rem;
    }

    div[data-testid="stMetric"] {
      padding: .2rem 0;
    }

    div[data-testid="stMetricLabel"] {
      font-size: .78rem;
    }

    div[data-testid="stMetricValue"] {
      font-size: 1.35rem;
    }

    hr {
      margin-top: .8rem !important;
      margin-bottom: .9rem !important;
    }

    [data-testid="stDataFrame"] {
      border: 1px solid var(--vv-border);
      border-radius: 10px;
      overflow: hidden;
    }

    @media (max-width: 900px) {
      .block-container {
        padding-left: .8rem;
        padding-right: .8rem;
      }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    profiles = pd.read_csv(APP_DATA_DIR / "archetype_profiles.csv")
    results = pd.read_csv(APP_DATA_DIR / "deck_results.csv")
    results["event_date"] = pd.to_datetime(results["event_date"]).dt.date
    return profiles, results


def windowed_results(results: pd.DataFrame, days: int) -> pd.DataFrame:
    if results.empty:
        return results.copy()

    as_of = max(results["event_date"])
    cutoff = as_of - timedelta(days=days - 1)
    return results[results["event_date"] >= cutoff].copy()


def metagame_table(
    profiles: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    counts = (
        results.groupby("cluster_id")
        .size()
        .rename("window_decks")
        .reset_index()
    )

    total = int(counts["window_decks"].sum()) if not counts.empty else 0

    merged = profiles.merge(counts, on="cluster_id", how="left")
    merged["window_decks"] = merged["window_decks"].fillna(0).astype(int)
    merged["window_meta_percent"] = (
        100.0 * merged["window_decks"] / total if total else 0.0
    )

    merged = merged[merged["window_decks"] > 0].copy()

    return merged.sort_values(
        ["window_decks", "archetype_name"],
        ascending=[False, True],
    )


def safe_signature(row) -> list[str]:
    signature = [
        row.get("signature_card_1", ""),
        row.get("signature_card_2", ""),
        row.get("signature_card_3", ""),
    ]
    return [x for x in signature if isinstance(x, str) and x]


def render_compact_card(row, days: int):
    image_url = row.get("signature_image_url")
    signature = safe_signature(row)

    cluster_id = escape(str(row["cluster_id"]), quote=True)
    archetype_name = escape(str(row["archetype_name"]))
    signature_text = " • ".join(escape(str(x)) for x in signature) if signature else "&nbsp;"

    if isinstance(image_url, str) and image_url:
        image_html = (
            f'<img class="vv-card-image" '
            f'src="{escape(image_url, quote=True)}" '
            f'alt="{archetype_name}">'
        )
    else:
        image_html = '<div class="vv-card-image-placeholder">No image</div>'

    href = f"?archetype={cluster_id}&days={int(days)}"

    st.markdown(
        f"""
        <a class="vv-card-link" href="{href}" target="_self">
          {image_html}
          <div class="vv-card-title">{archetype_name}</div>
          <div class="vv-signature">{signature_text}</div>
          <div class="vv-card-stats">
            <div>
              <div class="vv-card-stat-main">{row["window_meta_percent"]:.1f}%</div>
              <div class="vv-card-stat-label">Meta</div>
            </div>
            <div style="text-align:right">
              <div class="vv-card-stat-main">{int(row["window_decks"])}</div>
              <div class="vv-card-stat-label">Decks</div>
            </div>
          </div>
          <div class="vv-card-cta">View archetype →</div>
        </a>
        """,
        unsafe_allow_html=True,
    )

def render_home(profiles, all_results, days):
    results = windowed_results(all_results, days)
    meta = metagame_table(profiles, results)

    as_of = max(all_results["event_date"]) if not all_results.empty else None

    st.markdown('<div class="vv-header">', unsafe_allow_html=True)
    st.title("Value Vintage Metagame")
    st.markdown("</div>", unsafe_allow_html=True)

    if as_of:
        st.markdown(
            f'<div class="vv-subtitle">'
            f'Online tournaments · Last {days} days · '
            f'Through {as_of.strftime("%B %-d, %Y")}'
            f'</div>',
            unsafe_allow_html=True,
        )

    m1, m2, m3 = st.columns([1, 1, 1])
    m1.metric("Deck Results", len(results))
    m2.metric("Events", results["event_url"].nunique())
    m3.metric("Archetypes", len(meta))

    st.divider()

    cols_per_row = 5
    for start in range(0, len(meta), cols_per_row):
        chunk = meta.iloc[start : start + cols_per_row]
        cols = st.columns(cols_per_row, gap="small")

        for col, (_, row) in zip(cols, chunk.iterrows()):
            with col:
                render_compact_card(row, days)


def render_archetype(profiles, all_results, days, cluster_id):
    result_window = windowed_results(all_results, days)
    profile_match = profiles[profiles["cluster_id"] == cluster_id]

    if profile_match.empty:
        st.error("That archetype was not found.")
        if st.button("Back to metagame"):
            st.query_params.clear()
            st.query_params["days"] = str(days)
            st.rerun()
        return

    profile = profile_match.iloc[0]
    rows = result_window[result_window["cluster_id"] == cluster_id].copy()

    if st.button("← Back to metagame"):
        st.query_params.clear()
        st.query_params["days"] = str(days)
        st.rerun()

    left, right = st.columns([1.05, 4.6], gap="large")

    with left:
        image_url = profile.get("signature_image_url")
        if isinstance(image_url, str) and image_url:
            st.image(image_url, width="stretch")

    with right:
        st.title(profile["archetype_name"])

        signature = safe_signature(profile)
        if signature:
            st.caption(" • ".join(signature))

        total_results = len(result_window)
        pct = (100 * len(rows) / total_results) if total_results else 0

        st.markdown(
            f"""
            <div class="vv-detail-meta">
              <div class="vv-detail-item">
                <div class="vv-detail-value">{pct:.1f}%</div>
                <div class="vv-detail-label">Meta</div>
              </div>
              <div class="vv-detail-item">
                <div class="vv-detail-value">{len(rows)}</div>
                <div class="vv-detail-label">Deck Results</div>
              </div>
              <div class="vv-detail-item">
                <div class="vv-detail-value">{rows["deck_id"].nunique() if not rows.empty else 0}</div>
                <div class="vv-detail-label">Unique Lists</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader(f"Tournament results — last {days} days")

    if rows.empty:
        st.info("No results for this archetype in the selected time window.")
        return

    rows = rows.sort_values(
        ["event_date", "placement"],
        ascending=[False, True],
    )

    display = rows[
        [
            "event_date",
            "event_name",
            "placement",
            "player",
            "record_raw",
            "submitted_archetype",
            "deck_url",
            "event_url",
        ]
    ].rename(
        columns={
            "event_date": "Date",
            "event_name": "Event",
            "placement": "Place",
            "player": "Player",
            "record_raw": "Record",
            "submitted_archetype": "Submitted Archetype",
            "deck_url": "Decklist",
            "event_url": "Event Page",
        }
    )

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(640, 42 + 35 * len(display)),
        column_config={
            "Date": st.column_config.DateColumn(
                "Date",
                format="MMM D, YYYY",
                width="small",
            ),
            "Event": st.column_config.TextColumn(
                "Event",
                width="large",
            ),
            "Place": st.column_config.NumberColumn(
                "Place",
                width="small",
            ),
            "Player": st.column_config.TextColumn(
                "Player",
                width="medium",
            ),
            "Record": st.column_config.TextColumn(
                "Record",
                width="small",
            ),
            "Submitted Archetype": st.column_config.TextColumn(
                "Submitted Archetype",
                width="medium",
            ),
            "Decklist": st.column_config.LinkColumn(
                "Deck",
                display_text="Moxfield",
                width="small",
            ),
            "Event Page": st.column_config.LinkColumn(
                "Source",
                display_text="VVMTG",
                width="small",
            ),
        },
    )


def main():
    required = [
        APP_DATA_DIR / "archetype_profiles.csv",
        APP_DATA_DIR / "deck_results.csv",
    ]
    missing = [p for p in required if not p.exists()]

    if missing:
        st.error(
            "App data is missing. Run `python build_data.py --days 90` first."
        )
        st.stop()

    profiles, results = load_data()

    with st.sidebar:
        st.subheader("Metagame")
        query_days = st.query_params.get("days")
        try:
            default_days = int(query_days) if query_days is not None else 90
        except (TypeError, ValueError):
            default_days = 90

        if default_days not in {30, 60, 90}:
            default_days = 90

        days = st.segmented_control(
            "Time period",
            [30, 60, 90],
            default=default_days,
            format_func=lambda x: f"{x}d",
        )
        if days is None:
            days = 90

        st.caption(
            "25 shared mainboard nonland card slots. "
            "Copies count individually; clustering is non-transitive."
        )

    cluster_id = st.query_params.get("archetype")

    if cluster_id:
        render_archetype(
            profiles,
            results,
            int(days),
            cluster_id,
        )
    else:
        render_home(
            profiles,
            results,
            int(days),
        )


if __name__ == "__main__":
    main()
