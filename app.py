"""
Loan Compliance System
=======================
A Streamlit recreation of the "Loan Compliance System" dashboard:
Deterministic Rule Enforcement & Agentic Remediation.

WHAT THIS FILE CONTAINS
------------------------
1. Configuration / constants          (colours, currencies, rule thresholds)
2. A light-theme CSS block            (search "CSS THEME" below)
3. A data layer with THREE swappable data sources:
       - "demo"   : auto-generated synthetic data (default, works instantly)
       - "csv"    : your own CSV export
       - "custom" : your own function - e.g. pulling structured records out
                    of PDFs via a vector store, and/or an LLM extraction step
   (search "DATA SOURCE" below for exactly where to plug in your own data)
4. Small formatting/HTML helper functions
5. Four page sections, switched via a lightweight nav control (not
   st.tabs() - see the "MAIN ENTRY POINT" section for why):
       - Review Workdesk
       - Compliance & Portfolio Report
       - OPA Rego Playground   (illustrative demo, not a real OPA engine)
       - Asset Value Predictor (heuristic demo, not a trained ML model)

WHO THIS FILE IS FOR
---------------------
This is written to be readable by a non-developer ("techno-functional")
reviewer as well as a developer who will eventually productionise it.
Every section that you are expected to edit before going live is marked
with a comment block starting with ">>> REPLACE ME <<<".

PERFORMANCE NOTE
-----------------
Only the currently-selected section's render function ever runs. Streamlit's
built-in st.tabs() renders every tab's code on every rerun (it only hides
the inactive ones with CSS), which made the whole app feel slow once real
data volumes were involved. This file uses st.segmented_control() as a
"which section is active" switch instead, and an if/elif in main() calls
only the matching render_*() function - see main() at the bottom of this
file.

HOW TO RUN IT
--------------
See the separate step-by-step guide document for a non-developer walk-
through. In short:
    pip install -r requirements.txt
    streamlit run app.py
"""

# Makes modern type hints like `tuple[str, int]` work on older Python 3
# versions too (not just 3.9+). Must be the very first import in the file.
from __future__ import annotations

# -----------------------------------------------------------------------------
# STANDARD LIBRARY IMPORTS
# -----------------------------------------------------------------------------
import io
import random
from datetime import datetime

# -----------------------------------------------------------------------------
# THIRD-PARTY IMPORTS
# -----------------------------------------------------------------------------
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =============================================================================
# 1. PAGE CONFIG
#    Streamlit needs this to be the first Streamlit command executed.
# =============================================================================
st.set_page_config(
    page_title="Loan Compliance System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# 2. DATA SOURCE SWITCH
#    This is the single control that decides where the loan portfolio comes
#    from. Change DATA_SOURCE_MODE to point the app at your real data once
#    it's ready. See the "DATA SOURCE ADAPTERS" section further down for the
#    exact functions you need to fill in for "csv" and "custom".
# =============================================================================
#   "demo"    -> auto-generate a synthetic 100,000-loan portfolio.
#                This is the default so the app runs immediately with no
#                setup. Good for demos, UI testing, and screenshots.
#   "csv"     -> load the portfolio from a CSV file on disk (CSV_DATA_PATH
#                below). Use this once you can export a CSV from your own
#                system in the format documented in load_data_from_csv().
#   "custom"  -> call your own Python function, load_data_from_custom_source()
#                (documented below). Use this for anything more advanced:
#                a live database/API call, text extracted from PDFs and
#                embedded into a vector store, and/or fields extracted from
#                free text using an LLM.
#
# >>> REPLACE ME <<< change this value when you are ready to use real data.
DATA_SOURCE_MODE = "demo"  # one of: "demo", "csv", "custom"

# >>> REPLACE ME <<< only used when DATA_SOURCE_MODE == "csv".
# Point this at a CSV file that has the columns listed in EXPORT_COLUMNS
# further down this file.
CSV_DATA_PATH = "data/my_loan_portfolio.csv"

# =============================================================================
# 3. DOMAIN CONSTANTS
#    Business rules, currencies, and vocabulary used to build/evaluate the
#    loan portfolio. These are what the three compliance rules are checked
#    against - tune them to match your real policy.
# =============================================================================

# FX_RATES: units of foreign currency per 1 EUR (i.e. "1 EUR = 1.1515 USD").
# >>> REPLACE ME <<< when you have a real FX feed, swap this dict for a
# live lookup (e.g. a call to an FX rates API) instead of a fixed table.
FX_RATES = {
    "EUR": 1.0,
    "USD": 1.1515,
    "GBP": 0.8660,
    "CHF": 0.9520,
    "JPY": 171.50,
    "SGD": 1.5520,
}
CURRENCY_LIST = list(FX_RATES.keys())
# Relative sampling weights used ONLY by the synthetic demo generator below
# (i.e. how often each currency shows up in the fake data). Not relevant
# once you plug in real data.
CURRENCY_WEIGHTS_DEMO = [0.38, 0.30, 0.17, 0.07, 0.05, 0.03]  # EUR,USD,GBP,CHF,JPY,SGD

# ---- The three deterministic compliance rules -------------------------------
# Rule 1 - Min Value:      the loan's EUR value must clear a minimum floor.
# Rule 2 - Currency:       the loan must be settled in an approved currency.
# Rule 3 - Asset Coverage: pledged collateral must cover a minimum % of the
#                          loan value (coverage = asset_value_eur / loan_value_eur).
# >>> REPLACE ME <<< with your organisation's real policy thresholds.
APPROVED_CURRENCIES = {"EUR", "USD", "GBP"}  # Rule 2
MIN_COVERAGE_PCT = 50.0  # Rule 3 (in percent)
MIN_VALUE_PERCENTILE_DEMO = 10  # Rule 1, demo data only:
# bottom 10% of loan values fail.
# Replace with a fixed EUR
# amount (e.g. MIN_LOAN_VALUE_EUR
# = 50_000) once you have real data.

# The five possible "review states" a loan can be in once a human/agent has
# looked at a compliance failure. "Clean / Passed" is reserved for loans
# that pass all three rules and therefore never need review.
REVIEW_STATES = ["Unreviewed", "Remediated (AI/Manual)", "Removed", "Ignored"]

# Columns every adapter must return (see "DATA SOURCE ADAPTERS" section).
# This is also the column order used by the CSV export/import buttons.
EXPORT_COLUMNS = [
    "loan_id",
    "company",
    "country",
    "currency",
    "loan_value",
    "loan_value_eur",
    "asset_type",
    "asset_value",
    "asset_value_eur",
    "coverage_pct",
    "rule1_pass",
    "rule2_pass",
    "rule3_pass",
    "overall_pass",
    "review_state",
]

# ---- Vocabulary used ONLY by the synthetic demo data generator --------------
# None of this is used once you switch DATA_SOURCE_MODE away from "demo".
DEMO_COMPANY_PREFIXES = [
    "Nordic",
    "Sovereign",
    "Helios",
    "Orion",
    "Zenith",
    "Nexus",
    "Apex",
    "Bavaria",
    "Titan",
    "Pacific",
    "Atlas",
    "Meridian",
    "Vertex",
    "Cobalt",
    "Summit",
    "Falcon",
    "Crown",
    "Silver",
    "Iron",
    "Quantum",
    "Aurora",
    "Cascade",
    "Obsidian",
    "Granite",
    "Vanguard",
    "Halcyon",
    "Ember",
]
DEMO_COMPANY_SUFFIXES = [
    "Telecom",
    "Materials",
    "Corp",
    "Holdings",
    "Motors",
    "Infrastructure",
    "Pharmaceuticals",
    "Real Estate",
    "Energy",
    "Group",
    "Industries",
    "Capital",
    "Logistics",
    "Systems",
    "Dynamics",
    "Technologies",
    "Partners",
]
DEMO_COUNTRIES = [
    "United States",
    "Japan",
    "Spain",
    "Netherlands",
    "France",
    "United Kingdom",
    "Italy",
    "Singapore",
    "Germany",
    "Switzerland",
    "Canada",
    "Australia",
    "Sweden",
    "Ireland",
    "Belgium",
    "Denmark",
]
DEMO_ASSET_TYPES = [
    "Global Patent Portfolio & Proprietary Trade Secrets",
    "Pharmaceuticals Primary Manufacturing Facility & Cold Storage",
    "Finished Goods Warehouse Inventory Lot #106",
    "Prime Logistics Distribution Center & HQ Land Plot",
    "Automated Robotic Assembly Line & Heavy Equipment",
    "Corporate HQ Tower & Adjacent Parking Structure",
    "Commercial Aircraft Fleet & Maintenance Hangars",
    "Data Center Campus & Network Infrastructure",
    "Renewable Energy Wind Farm Assets",
    "Retail Flagship Portfolio & Store Inventory",
]

# =============================================================================
# 4. LIGHT THEME COLOUR PALETTE
#    Every colour used anywhere in the app (CSS + Plotly charts) is defined
#    here once, so re-theming later only means editing this dictionary.
# =============================================================================
COLORS = {
    # page chrome
    "app_bg": "#f4f6fb",  # overall page background
    "card_bg": "#ffffff",  # card / panel background
    "card_border": "#e3e7f0",  # light border around cards
    "header_bg": "#ffffff",  # top header bar background
    # text
    "text_primary": "#1f2430",  # headings / high-emphasis text
    "text_secondary": "#6b7280",  # captions / secondary labels
    "text_muted": "#94a1b8",  # faint helper text
    # brand / accent
    "indigo": "#6d5ce8",  # primary buttons, active tab, links
    "indigo_bright": "#8577f2",
    "indigo_soft": "#efecfd",  # pale indigo background for tints
    # status colours (readable on a WHITE background)
    "green": "#15803d",
    "green_soft": "#dcfce7",
    "red": "#c0273c",
    "red_soft": "#fde3e7",
    "orange": "#b45309",
    "orange_soft": "#fef3c7",
    "blue": "#2563eb",
    "blue_soft": "#dbeafe",
    "purple": "#7c3aed",
    "purple_soft": "#ede9fe",
    "grey": "#64748b",
    "grey_soft": "#eef1f6",
}


# =============================================================================
# 5. CSS THEME (light)
#    Streamlit doesn't have a first-class theming API for every element we
#    use (pills, badges, custom cards), so we inject a small stylesheet.
#    Everything here reads its colours from COLORS above where practical.
# =============================================================================
def inject_css() -> None:
    """Inject the app's light-theme stylesheet once per page render."""
    c = COLORS
    st.markdown(
        f"""
        <style>
        /* ---- page background & basic layout ------------------------------ */
        .stApp {{ background-color: {c['app_bg']}; }}
        /* Hide Streamlit's default chrome entirely (hamburger menu, the
           colourful "deploy" toolbar, the top decoration line, and the
           footer). Earlier this was just made transparent, which still
           reserved a blank white strip at the top of the page - hiding it
           outright removes that space completely. */
        #MainMenu {{ visibility: hidden; height: 0; }}
        header[data-testid="stHeader"] {{ display: none; }}
        div[data-testid="stToolbar"] {{ display: none; }}
        div[data-testid="stDecoration"] {{ display: none; }}
        footer {{ visibility: hidden; height: 0; }}
        div.block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1800px; }}
        * {{ font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}

        /* ---- top header shell --------------------------------------------- */
        /* Targets the st.container(key="lcs_header") from render_header()
           directly - Streamlit maps a container's key= to a CSS class named
           "st-key-<key>" on that exact element, which is a more robust way
           to style a container than wrapping it in a hand-written, easily
           mis-nested <div> via st.markdown(). */
        .st-key-lcs_header {{
            background: {c['header_bg']} !important;
            border: 1px solid {c['card_border']};
            border-radius: 14px;
            padding: 16px 22px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04);
        }}
        .lcs-title {{ font-size: 26px; font-weight: 800; color: {c['text_primary']}; margin: 0; line-height: 1.1; }}
        .lcs-subtitle {{ color: {c['text_secondary']}; font-size: 12.5px; margin-top: 2px; }}
        .lcs-pill {{
            display: inline-block; background: {c['indigo_soft']};
            border: 1px solid #cfc7fb; color: #4c3fb8;
            border-radius: 8px; padding: 8px 14px; font-weight: 600; font-size: 13.5px;
            white-space: nowrap;
        }}
        /* Each stat chip (Total Audited / Failures / Remediated / FX Source)
           is a flex item inside the header's horizontal container. flex:0 0
           auto keeps it sized to its own content instead of being stretched
           or shrunk by the flexbox - it just wraps onto a new line, as a
           whole unit, if the row runs out of width. */
        .lcs-stat-block {{ flex: 0 0 auto; white-space: nowrap; }}
        .lcs-stat-label {{ color: {c['text_secondary']}; font-size: 11.5px; }}
        .lcs-stat-value {{ font-size: 19px; font-weight: 800; color: {c['text_primary']}; }}
        .lcs-stat-value.red {{ color: {c['red']}; }}
        .lcs-stat-value.green {{ color: {c['green']}; }}
        .lcs-stat-value.blue {{ color: {c['blue']}; }}

        /* ---- generic cards -------------------------------------------------- */
        .card {{
            background: {c['card_bg']}; border: 1px solid {c['card_border']}; border-radius: 14px;
            padding: 18px 20px; height: 100%;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        }}
        .card-label {{
            color: {c['text_secondary']}; font-size: 13.5px;
            display:flex; justify-content: space-between; align-items:center;
        }}
        .card-value {{ font-size: 30px; font-weight: 800; color: {c['text_primary']}; margin: 6px 0 2px 0; }}
        .card-sub {{ color: {c['text_secondary']}; font-size: 12.5px; }}
        .card-value.green {{ color: {c['green']}; }}
        .card-value.red {{ color: {c['red']}; }}
        .card-value.indigo {{ color: {c['indigo']}; }}

        .section-card {{
            background: {c['card_bg']}; border: 1px solid {c['card_border']}; border-radius: 14px;
            padding: 22px 24px; margin-bottom: 16px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        }}
        .section-title {{ font-size: 20px; font-weight: 800; color: {c['text_primary']}; margin:0; }}
        .section-sub {{ color: {c['text_secondary']}; font-size: 13.5px; margin-top: 4px; }}
        .panel-title {{ font-size: 17px; font-weight: 700; color: {c['text_primary']}; margin-bottom: 2px; }}
        .panel-sub {{ color: {c['text_secondary']}; font-size: 12.5px; margin-bottom: 6px; }}
        .panel-text {{ color: {c['text_secondary']}; font-size: 13.5px; line-height: 1.6; }}

        /* ---- badges / pills -------------------------------------------------- */
        .pill {{ display:inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; }}
        .pill-unreviewed {{ background: {c['red_soft']}; color: {c['red']}; border: 1px solid #f6c4cd; }}
        .pill-remediated {{ background: {c['purple_soft']}; color: {c['purple']}; border: 1px solid #d9cdf9; }}
        .pill-removed    {{ background: {c['red_soft']}; color: {c['red']}; border: 1px solid #f2a8b4; }}
        .pill-ignored    {{ background: {c['grey_soft']}; color: {c['grey']}; border: 1px solid #dde2ea; }}
        .pill-clean      {{ background: {c['green_soft']}; color: {c['green']}; border: 1px solid #b8ecc9; }}

        .rule-badge {{
            display:inline-block; padding: 2px 7px; border-radius: 5px;
            font-size: 11px; font-weight: 800; margin-right: 4px;
        }}
        .rule-pass {{ background: {c['green_soft']}; color: {c['green']}; }}
        .rule-fail {{ background: {c['red_soft']}; color: {c['red']}; }}

        .cov-green {{ color: {c['green']}; font-weight: 700; }}
        .cov-red {{ color: {c['red']}; font-weight: 700; }}

        /* ---- workdesk table row text ----------------------------------------- */
        .row-loanid    {{ font-weight: 700; color: {c['text_primary']}; font-size: 14px; }}
        .row-company   {{ font-weight: 700; color: {c['text_primary']}; font-size: 13.5px; }}
        .row-country   {{ color: {c['text_secondary']}; font-size: 12px; }}
        .row-primary   {{ color: {c['text_primary']}; font-size: 13.5px; font-weight: 700; }}
        .row-secondary {{ color: {c['text_secondary']}; font-size: 11.5px; }}
        .row-asset     {{ color: {c['text_primary']}; font-size: 13px; }}

        .lcs-col-header {{
            color: {c['text_secondary']}; font-size: 11px; font-weight: 800; letter-spacing: 0.04em;
            text-transform: uppercase; padding-bottom: 6px; border-bottom: 1px solid {c['card_border']};
            margin-bottom: 8px;
        }}
        .lcs-divider {{ border-bottom: 1px solid {c['card_border']}; margin: 4px 0 4px 0; }}

        /* ---- buttons ---------------------------------------------------------- */
        div.stButton > button, div.stDownloadButton > button {{
            border-radius: 9px; font-weight: 700; font-size: 13.5px; border: 1px solid {c['card_border']};
        }}
        /* Slightly tighter horizontal padding, scoped to just the header's
           Import/Reset/Export button group, buys back a bit of width so the
           trio comfortably fits on the header's first line at typical
           desktop widths instead of always wrapping to its own line. */
        .st-key-lcs_header_actions button {{ padding-left: 12px !important; padding-right: 12px !important; }}
        div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {{
            background: linear-gradient(180deg, {c['indigo_bright']}, {c['indigo']}); border: none; color: white;
        }}
        div.stButton > button[kind="secondary"], div.stDownloadButton > button[kind="secondary"] {{
            background: #f7f8fb; color: {c['text_primary']};
        }}
        div[data-testid="stPopover"] > button {{
            background: linear-gradient(180deg, {c['indigo_bright']}, {c['indigo']}) !important;
            color: white !important; border: none !important; border-radius: 9px !important;
            font-weight: 700 !important; font-size: 13px !important;
        }}

        /* ---- section nav (st.segmented_control) -------------------------------- */
        /* Accent colour for the selected segment comes from .streamlit/config.toml
           (theme.primaryColor) so it stays in sync with the rest of the app. */
        div[data-testid="stSegmentedControl"] {{ margin-bottom: 4px; }}

        /* ---- captions / secondary status text ------------------------------------ */
        /* Belt-and-suspenders: Streamlit's built-in st.caption() renders quite
           faint on a light background. Where legibility matters we use this
           class on our own markdown instead of st.caption(); this rule also
           darkens any remaining st.caption() text app-wide as a safety net. */
        .wd-status-text {{ color: {c['text_primary']}; font-size: 13.5px; opacity: 0.85; }}
        small, [data-testid="stCaptionContainer"] {{ color: {c['text_secondary']} !important; opacity: 1 !important; }}

        /* ---- form inputs -------------------------------------------------------- */
        input, textarea, .stSelectbox div[data-baseweb="select"] > div {{
            background-color: #ffffff !important;
            border-color: {c['card_border']} !important;
            color: {c['text_primary']} !important;
        }}
        [data-testid="stMetricValue"] {{ color: {c['text_primary']}; }}
        hr {{ border-color: {c['card_border']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# 6. SYNTHETIC DEMO DATA GENERATOR
#    Produces a realistic-looking loan portfolio out of thin air, purely so
#    the app has something to show on first run. This whole function
#    becomes irrelevant once DATA_SOURCE_MODE is "csv" or "custom" - it is
#    only called when DATA_SOURCE_MODE == "demo".
# =============================================================================
@st.cache_data(show_spinner=False)
def generate_demo_loans(n: int, seed: int) -> pd.DataFrame:
    """
    Generate a synthetic portfolio of ``n`` loans for demo purposes.

    Parameters
    ----------
    n : int
        Number of loans to generate (the app calls this with n=100_000).
    seed : int
        Random seed. Changing the seed (e.g. via the "Reset 100k" button)
        produces a fresh random portfolio.

    Returns
    -------
    pandas.DataFrame
        One row per loan, with all columns listed in EXPORT_COLUMNS.
    """
    rng = np.random.default_rng(seed)

    # -- currency & headline loan value ------------------------------------
    currency = rng.choice(CURRENCY_LIST, size=n, p=CURRENCY_WEIGHTS_DEMO)
    loan_value_eur = rng.lognormal(mean=13.02, sigma=1.5, size=n)
    loan_value_eur = np.clip(loan_value_eur, 500, 50_000_000)

    # -- pledged collateral value, expressed as a coverage percentage -----
    coverage_pct = rng.beta(3.55, 2.0, size=n) * 120
    coverage_pct = np.clip(coverage_pct, 5, 145)
    asset_value_eur = loan_value_eur * coverage_pct / 100.0

    # -- convert EUR amounts back into each loan's native currency --------
    rate_per_loan = np.array([FX_RATES[cur] for cur in currency])
    loan_value_native = loan_value_eur * rate_per_loan
    asset_value_native = asset_value_eur * rate_per_loan

    # -- evaluate the three deterministic compliance rules -----------------
    min_value_threshold_eur = np.percentile(loan_value_eur, MIN_VALUE_PERCENTILE_DEMO)
    rule1_pass = loan_value_eur >= min_value_threshold_eur
    rule2_pass = np.isin(currency, list(APPROVED_CURRENCIES))
    rule3_pass = coverage_pct >= MIN_COVERAGE_PCT
    overall_pass = rule1_pass & rule2_pass & rule3_pass

    # -- cosmetic fields: company name, HQ country, pledged asset type ----
    prefixes = rng.choice(DEMO_COMPANY_PREFIXES, size=n)
    suffixes = rng.choice(DEMO_COMPANY_SUFFIXES, size=n)
    has_batch_number = rng.random(n) < 0.18
    batch_numbers = rng.choice(["10", "20", "30", "40", "50"], size=n)
    company_names = np.array(
        [
            f"{prefix} {suffix}" + (f" {num}" if add_num else "")
            for prefix, suffix, add_num, num in zip(prefixes, suffixes, has_batch_number, batch_numbers)
        ]
    )
    country = rng.choice(DEMO_COUNTRIES, size=n)
    asset_type = rng.choice(DEMO_ASSET_TYPES, size=n)

    # Loans that pass every rule never need review; everything else starts
    # life in the Review Workdesk as "Unreviewed".
    review_state = np.where(overall_pass, "Clean / Passed", "Unreviewed")

    return pd.DataFrame(
        {
            "loan_id": [f"LN-{100000 + i}" for i in range(n)],
            "company": company_names,
            "country": country,
            "currency": currency,
            "loan_value": loan_value_native.round(2),
            "loan_value_eur": loan_value_eur.round(2),
            "asset_type": asset_type,
            "asset_value": asset_value_native.round(2),
            "asset_value_eur": asset_value_eur.round(2),
            "coverage_pct": coverage_pct.round(1),
            "rule1_pass": rule1_pass,
            "rule2_pass": rule2_pass,
            "rule3_pass": rule3_pass,
            "overall_pass": overall_pass,
            "review_state": review_state,
        }
    )


# =============================================================================
# 7. DATA SOURCE ADAPTERS  <-- start here when connecting your own data
# =============================================================================
# Every adapter below must return a pandas DataFrame with exactly the columns
# listed in EXPORT_COLUMNS (defined near the top of this file). That
# contract is what lets the rest of the app - the header stats, the Review
# Workdesk table, the charts - work unchanged no matter where the data came
# from.
#
# REQUIRED OUTPUT SCHEMA (one row per loan):
#   loan_id          str    unique identifier, e.g. "LN-100001"
#   company          str    borrower / company name
#   country          str    borrower HQ country
#   currency         str    ISO currency code of the loan, e.g. "EUR", "USD"
#   loan_value       float  loan amount in its native currency
#   loan_value_eur   float  loan amount converted to EUR
#   asset_type       str    description of the pledged collateral
#   asset_value      float  pledged asset value, in the loan's native currency
#   asset_value_eur  float  pledged asset value converted to EUR
#   coverage_pct     float  = asset_value_eur / loan_value_eur * 100
#   rule1_pass       bool   True if the loan clears the Min Value rule
#   rule2_pass       bool   True if the loan currency is on the approved list
#   rule3_pass       bool   True if coverage_pct >= MIN_COVERAGE_PCT
#   overall_pass     bool   rule1_pass and rule2_pass and rule3_pass
#   review_state     str    one of: "Clean / Passed", "Unreviewed",
#                           "Remediated (AI/Manual)", "Removed", "Ignored"
#
# If your source data does not already contain rule1_pass / rule2_pass /
# rule3_pass / overall_pass, you can compute them the same way
# generate_demo_loans() does above - see the "evaluate the three
# deterministic compliance rules" block for the exact formulas.
# -----------------------------------------------------------------------------


def load_data_from_csv(csv_path: str) -> pd.DataFrame:
    """
    OPTION A: Load the loan portfolio from a CSV file on disk.

    >>> REPLACE ME <<<
    This already works as-is for any CSV that has the required columns
    (see the schema above) - just point CSV_DATA_PATH at your file and set
    DATA_SOURCE_MODE = "csv" near the top of this file.

    Typical sources for that CSV: an export from your loan origination
    system, a nightly data-warehouse extract, or an ETL job that already
    joins loan + collateral + FX data together.

    Parameters
    ----------
    csv_path : str
        Path to a CSV file with (at least) the columns in EXPORT_COLUMNS.

    Returns
    -------
    pandas.DataFrame
    """
    df = pd.read_csv(csv_path)
    missing_columns = [col for col in EXPORT_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"'{csv_path}' is missing required column(s): {missing_columns}. "
            f"See the EXPORT_COLUMNS schema at the top of app.py."
        )
    return df


def load_data_from_pdf_vectors(pdf_folder_path: str) -> pd.DataFrame:
    """
    OPTION B: Build the loan table from PDF documents via a vector store.

    >>> REPLACE ME <<<
    This function is a STUB - it shows the shape of the pipeline but does
    not call any real PDF/embedding/vector-store libraries, so nothing here
    will run until you fill in your own client code. A typical
    implementation looks like this:

        1. Extract text from each PDF (e.g. with `pdfplumber`, `PyPDF2`, or
           an OCR pipeline such as `pytesseract` for scanned documents).
        2. Split the text into chunks and turn each chunk into a vector
           embedding (e.g. using an OpenAI/Anthropic/local embedding model).
        3. Store the vectors in your vector database of choice (Pinecone,
           Weaviate, FAISS, pgvector, Chroma, etc.) alongside the source
           document's metadata (loan ID, filename, page number...).
        4. For each loan, retrieve the most relevant chunks and pass them to
           an LLM with a prompt asking it to return the structured fields
           you need (loan value, currency, pledged asset, ...) as JSON -
           see load_data_from_llm_extraction() below for that step.
        5. Collect the extracted rows into a list of dicts and return
           pd.DataFrame(list_of_dicts).

    Parameters
    ----------
    pdf_folder_path : str
        Folder containing the source PDF documents (loan agreements,
        collateral appraisals, etc.).

    Returns
    -------
    pandas.DataFrame
    """
    # -------------------------------------------------------------------------
    # >>> REPLACE ME <<< illustrative skeleton only - nothing below actually
    # runs. Delete the NotImplementedError once you've wired in your own
    # PDF extraction + embedding + vector-store client.
    # -------------------------------------------------------------------------
    #
    # import glob
    # from your_pdf_library import extract_text_from_pdf
    # from your_embedding_client import embed_text_chunks
    # from your_vector_store_client import VectorStoreClient
    #
    # vector_store = VectorStoreClient(api_key="...", index_name="loan-docs")
    # extracted_rows = []
    # for pdf_path in glob.glob(f"{pdf_folder_path}/*.pdf"):
    #     raw_text = extract_text_from_pdf(pdf_path)
    #     chunks = chunk_text(raw_text, chunk_size=800, overlap=100)
    #     vectors = embed_text_chunks(chunks)
    #     vector_store.upsert(vectors, metadata={"source_file": pdf_path})
    #
    #     # Retrieve the most relevant chunks for this document and ask an
    #     # LLM to turn them into the structured fields our schema needs:
    #     relevant_chunks = vector_store.query(chunks, top_k=5)
    #     loan_record = extract_fields_with_llm(relevant_chunks)  # -> dict
    #     extracted_rows.append(loan_record)
    #
    # return pd.DataFrame(extracted_rows)

    raise NotImplementedError(
        "load_data_from_pdf_vectors() is a placeholder. Wire up your PDF "
        "text-extraction, embedding, and vector-store client, then remove "
        "this line. See the docstring above for the expected pipeline."
    )


def load_data_from_llm_extraction(source_texts) -> pd.DataFrame:
    """
    OPTION C: Use an LLM to extract structured loan records from free text.

    >>> REPLACE ME <<<
    Use this when your source material is unstructured text - credit
    committee memos, underwriter notes, emails, chat transcripts - rather
    than a clean CSV or a PDF-derived vector store. This is also the
    function you'd call downstream of load_data_from_pdf_vectors() above,
    once you have relevant text chunks to extract fields from.

    Typical implementation:
        1. For each loan's source text, send it to an LLM (Anthropic Claude,
           OpenAI, etc.) with a prompt asking for exactly ONE JSON object
           per loan, with keys matching the schema documented in the
           "DATA SOURCE ADAPTERS" section header above.
        2. Parse the JSON string the model returns into a Python dict.
        3. Validate/clean the values (currency codes, numeric types, etc.)
        4. Collect every parsed dict into a list and return
           pd.DataFrame(list_of_dicts).

    Parameters
    ----------
    source_texts : list[str]
        One string of free text per loan (e.g. a memo or note) that
        contains the information you need to extract.

    Returns
    -------
    pandas.DataFrame
    """
    # -------------------------------------------------------------------------
    # >>> REPLACE ME <<< illustrative skeleton only, using Anthropic's SDK as
    # an example - swap in whichever LLM provider you use. Delete the
    # NotImplementedError once this is wired up.
    # -------------------------------------------------------------------------
    #
    # import json
    # import anthropic
    #
    # client = anthropic.Anthropic(api_key="YOUR_API_KEY")
    # extraction_prompt_template = """
    # Extract the following fields from the loan memo below and return ONLY
    # a JSON object (no other text) with these exact keys: loan_id, company,
    # country, currency, loan_value, asset_type, asset_value.
    #
    # Loan memo:
    # {memo_text}
    # """
    #
    # extracted_rows = []
    # for memo_text in source_texts:
    #     response = client.messages.create(
    #         model="claude-sonnet-4-5",
    #         max_tokens=1000,
    #         messages=[{
    #             "role": "user",
    #             "content": extraction_prompt_template.format(memo_text=memo_text),
    #         }],
    #     )
    #     record = json.loads(response.content[0].text)
    #     extracted_rows.append(record)
    #
    # extracted_df = pd.DataFrame(extracted_rows)
    # # NOTE: you'll still need to compute loan_value_eur, asset_value_eur,
    # # coverage_pct, rule1_pass/rule2_pass/rule3_pass/overall_pass and
    # # review_state - reuse the formulas from generate_demo_loans() above.
    # return extracted_df

    raise NotImplementedError(
        "load_data_from_llm_extraction() is a placeholder. Wire up your LLM "
        "client and extraction prompt, then remove this line. See the "
        "docstring above for the expected pipeline."
    )


def load_data_from_custom_source() -> pd.DataFrame:
    """
    OPTION D: Your single entry point for "real" data once it's ready.

    >>> REPLACE ME <<<
    This is the function called when DATA_SOURCE_MODE = "custom" (see the
    switch near the top of this file). Point it at whichever adapter (or
    combination of adapters) makes sense for your pipeline - CSV, PDF +
    vector store, LLM extraction, a live database/API call, or several of
    these combined. A simple example:

        def load_data_from_custom_source() -> pd.DataFrame:
            csv_part = load_data_from_csv("data/system_export.csv")
            pdf_part = load_data_from_pdf_vectors("data/loan_pdfs/")
            return pd.concat([csv_part, pdf_part], ignore_index=True)

    Returns
    -------
    pandas.DataFrame
    """
    raise NotImplementedError(
        "load_data_from_custom_source() is a placeholder. Call your own "
        "adapter(s) here (load_data_from_csv / load_data_from_pdf_vectors / "
        "load_data_from_llm_extraction, or your own database/API call) and "
        "return a single combined DataFrame."
    )


def apply_remediation_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """
    Overlay any in-session remediation actions (Remediate / Ignore / Remove)
    on top of the base dataset. This keeps the "did a human/agent act on
    this exception" state separate from the underlying rule verdict, which
    matters no matter which DATA_SOURCE_MODE is active.
    """
    overrides = st.session_state.loan_overrides
    if not overrides:
        return df
    df = df.copy()
    overridden_mask = df["loan_id"].isin(overrides.keys())
    if overridden_mask.any():
        df.loc[overridden_mask, "review_state"] = df.loc[overridden_mask, "loan_id"].map(overrides)
    return df


# =============================================================================
# 8. FORMATTING / HTML HELPER FUNCTIONS
#    Small, pure functions that turn raw values into display strings or
#    small HTML snippets. Kept separate from the page-rendering functions so
#    they're easy to unit-test/reuse.
# =============================================================================
def fmt_number(value: float, decimals: int = 2) -> str:
    """Format a number with thousands separators, e.g. 12345.6 -> '12,345.60'."""
    return f"{value:,.{decimals}f}"


def fmt_eur_millions(value_eur_total: float) -> str:
    """Format a EUR total (e.g. a portfolio sum) in millions, e.g. '€138.10M'."""
    return f"€{value_eur_total / 1e6:,.2f}M"


def status_pill_html(review_state: str) -> str:
    """Return a coloured HTML 'pill' badge for a given review_state value."""
    style_by_state = {
        "Clean / Passed": ("pill-clean", "Clean / Passed"),
        "Unreviewed": ("pill-unreviewed", "Unreviewed"),
        "Remediated (AI/Manual)": ("pill-remediated", "Remediated"),
        "Removed": ("pill-removed", "Removed"),
        "Ignored": ("pill-ignored", "Ignored"),
    }
    css_class, label = style_by_state.get(review_state, ("pill-unreviewed", review_state))
    return f'<span class="pill {css_class}">{label}</span>'


def rule_badge_html(label: str, passed: bool) -> str:
    """Return a small coloured HTML badge (e.g. 'R1') showing pass/fail."""
    css_class = "rule-pass" if passed else "rule-fail"
    return f'<span class="rule-badge {css_class}">{label}</span>'


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialise the export-relevant columns of a DataFrame to CSV bytes."""
    export_df = df[EXPORT_COLUMNS].copy()
    buffer = io.StringIO()
    export_df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


# =============================================================================
# 9. SESSION STATE
#    Streamlit re-runs this whole script on every interaction, so anything
#    that needs to persist between reruns (the current random seed, which
#    loans have been remediated, which rows are checked, etc.) lives in
#    st.session_state.
# =============================================================================
def init_session_state() -> None:
    """Initialise every session_state key this app relies on, exactly once."""
    defaults = {
        "seed": 42,  # random seed for the demo data generator
        "loan_overrides": {},  # {loan_id: new_review_state}
        "custom_df": None,  # holds an imported CSV, if any
        "selected_ids": set(),  # loan_ids checked in the Review Workdesk
        "page": 1,  # current page in the Review Workdesk table
        "last_active_section": NAV_REVIEW_WORKDESK,  # sticky nav selection - see main()
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get_portfolio_data() -> pd.DataFrame:
    """
    Single entry point the rest of the app calls to get the current loan
    portfolio. Resolution order:
        1. A CSV imported this session via the header's "Import CSV" button
           always wins (it's an explicit user action).
        2. Otherwise, fall back to whatever DATA_SOURCE_MODE selects
           ("demo", "csv", or "custom" - see the switch near the top of
           this file).
    Any in-session remediation actions are then layered on top.
    """
    if st.session_state.custom_df is not None:
        base_df = st.session_state.custom_df
    elif DATA_SOURCE_MODE == "csv":
        base_df = load_data_from_csv(CSV_DATA_PATH)
    elif DATA_SOURCE_MODE == "custom":
        base_df = load_data_from_custom_source()
    else:  # DATA_SOURCE_MODE == "demo" (default)
        base_df = generate_demo_loans(100_000, st.session_state.seed)
    return apply_remediation_overrides(base_df)


def reset_demo_data() -> None:
    """Regenerate a brand-new random demo portfolio (the 'Reset 100k' button)."""
    st.session_state.seed = random.randint(1, 10_000_000)
    st.session_state.loan_overrides = {}
    st.session_state.custom_df = None
    st.session_state.selected_ids = set()
    st.session_state.page = 1
    generate_demo_loans.clear()  # drop the cached DataFrame for the old seed


# =============================================================================
# 10. HEADER
#     The top bar: title, "OPA Rego + AI Agent" pill, live stats, and the
#     Import / Reset / Export controls.
# =============================================================================
def render_header(df: pd.DataFrame) -> None:
    """Render the fixed header bar shown above all tabs."""
    total_audited = len(df)
    failing_mask = ~df["overall_pass"]
    unreviewed_failing = int((failing_mask & (df["review_state"] == "Unreviewed")).sum())
    remediated = int((df["review_state"] == "Remediated (AI/Manual)").sum())

    # A single horizontal flex row holds every header element: the logo +
    # title, the "OPA Rego + AI Agent" pill, the four live stat chips, and
    # the three action buttons.
    #
    # This used to be a fixed-ratio st.columns([3.4, 1.5, 1, 0.9, ...]) row
    # wrapped in a hand-rolled "open a <div>, add columns, close the </div>"
    # trick to give it the card background/border. Fixed-ratio columns never
    # wrap - they only ever shrink - so on any window narrower than a very
    # wide desktop, the "OPA Rego + AI Agent" pill (which has white-space:
    # nowrap) overflowed its shrinking column and rendered on top of the
    # "Total Audited" stat next to it, and the Import/Reset/Export buttons
    # (use_container_width=True in an increasingly narrow column) had their
    # labels wrap letter-by-letter.
    #
    # The fix uses a horizontal flex container (st.container(horizontal=
    # True, ...)), which wraps whole items onto a new line once they no
    # longer fit, so nothing ever overlaps or gets squeezed below its
    # natural size. The card's background/border/padding is applied via
    # key="lcs_header", which Streamlit turns into a stable ".st-key-
    # lcs_header" CSS class on this exact container - a supported,
    # version-proof alternative to the old unclosed-<div> trick (which
    # doesn't reliably wrap real Streamlit components, only raw markdown).
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        horizontal_alignment="distribute",
        gap="small",
        key="lcs_header",
    ):
        # -- logo + title -----------------------------------------------------
        st.markdown(
            """
            <div style="display:flex; align-items:center; gap:12px;">
              <div style="width:46px; height:46px; border-radius:12px; flex-shrink:0;
                          background:linear-gradient(135deg,#8577f2,#5b4fd1);
                          display:flex; align-items:center; justify-content:center; font-size:22px;">🛡️</div>
              <div>
                <div class="lcs-title">Loan Compliance System</div>
                <div class="lcs-subtitle">Deterministic Rule Enforcement &amp; Agentic Remediation</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # -- "OPA Rego + AI Agent" badge ---------------------------------------
        st.markdown('<div class="lcs-pill">🤖 OPA Rego + AI Agent</div>', unsafe_allow_html=True)

        # -- live stat chips ----------------------------------------------------
        st.markdown(
            f'<div class="lcs-stat-block"><div class="lcs-stat-label">Total Audited</div>'
            f'<div class="lcs-stat-value">{total_audited:,}'
            f'<span style="font-size:13px; font-weight:600; color:{COLORS["text_secondary"]};"> loans</span></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="lcs-stat-block"><div class="lcs-stat-label">Failures</div>'
            f'<div class="lcs-stat-value red">{unreviewed_failing:,}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="lcs-stat-block"><div class="lcs-stat-label">Remediated</div>'
            f'<div class="lcs-stat-value green">{remediated:,}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="lcs-stat-block"><div class="lcs-stat-label">FX Source</div>'
            f'<div class="lcs-stat-value blue" style="font-size:15px;">1 EUR = {FX_RATES["USD"]:.4f} USD</div></div>',
            unsafe_allow_html=True,
        )

        # -- action buttons ---------------------------------------------------
        # Import CSV / Reset 100k / Export Audit CSV sit directly in the same
        # outer container as everything else above (no nested sub-container).
        # A nested st.container() defaults its own width to "stretch" - 100%
        # of its parent - so wrapping these three in their own inner container
        # made THAT container claim a full line for itself and permanently
        # push the buttons onto row 2, no matter how much room was free.
        # Buttons/popovers default to a content-sized width instead, so left
        # as direct children here they simply sit inline and wrap onto a new
        # line only when the row actually runs out of space.
        #
        # None of the three use use_container_width=True any more: that
        # stretched each button to fill its (shrinking) st.columns() slot,
        # which is what forced their labels to wrap letter-by-letter. Left
        # at their natural content width, they simply wrap as a whole group
        # when needed.
        with st.popover("⬆️ Import CSV"):
            st.caption(
                "Upload a CSV previously exported from this app (or matching the "
                "same columns) to replace the current portfolio."
            )
            uploaded_file = st.file_uploader(
                "CSV file", type=["csv"], label_visibility="collapsed", key="csv_uploader"
            )
            if uploaded_file is not None:
                try:
                    imported_df = pd.read_csv(uploaded_file)
                    missing_columns = [col for col in EXPORT_COLUMNS if col not in imported_df.columns]
                    if missing_columns:
                        st.error(f"Missing columns: {', '.join(missing_columns)}")
                    else:
                        st.session_state.custom_df = imported_df
                        st.session_state.loan_overrides = {}
                        st.success(f"Loaded {len(imported_df):,} loans.")
                        st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                    st.error(f"Could not read CSV: {exc}")

        if st.button("🔄 Reset 100k", key="reset_btn"):
            reset_demo_data()
            st.rerun()

        st.download_button(
            "⬇️ Export Audit CSV",
            data=dataframe_to_csv_bytes(df),
            file_name=f"loan_compliance_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            type="primary",
            key="export_header_btn",
        )


# =============================================================================
# 11. TAB 1: REVIEW WORKDESK
#     Searchable/filterable table of loans, with per-row and bulk actions
#     for resolving compliance exceptions.
# =============================================================================
RULE_FILTER_OPTIONS = [
    "Failed Compliance (All)",
    "Rule 1: Min Value failures",
    "Rule 2: Currency failures",
    "Rule 3: Asset Coverage failures",
    "All Loans (Pass + Fail)",
]
REVIEW_FILTER_OPTIONS = ["All Review States", "Unreviewed", "Remediated (AI/Manual)", "Removed", "Ignored"]

# Column width ratios shared by the table header and every table row, so
# they stay visually aligned.
WORKDESK_COLUMN_WEIGHTS = [0.4, 1.0, 1.0, 1.9, 1.35, 2.15, 0.8, 1.25, 1.05]
WORKDESK_COLUMN_HEADERS = [
    "",
    "STATUS",
    "LOAN ID",
    "COMPANY & HQ",
    "LOAN VALUE",
    "PLEDGED ASSET",
    "COVERAGE",
    "RULE CHECKS",
    "ACTIONS",
]


def set_loan_review_state(loan_id: str, new_state: str) -> None:
    """Record a remediation decision for one loan (used by both the per-row
    action control and the bulk-action buttons)."""
    st.session_state.loan_overrides[loan_id] = new_state


def _apply_bulk_action(new_state: str) -> None:
    """
    Apply `new_state` to every currently-checked loan, then clear the
    selection. Passed to buttons via `on_click` (rather than the older
    `if st.button(...): ...; st.rerun()` pattern) so the change is applied
    BEFORE the script reruns, in the same interaction - avoiding a second,
    unnecessary rerun on every click.

    IMPORTANT: clearing `selected_ids` alone is not enough. Each row's
    checkbox is a real Streamlit widget with its OWN persisted value under
    key `chk_<loan_id>`; once a checkbox widget has been created, Streamlit
    keeps using that stored value on every future rerun and ignores the
    `value=` argument we pass it. If we only cleared `selected_ids`, the
    checkbox would still report itself as checked next render, and the
    row-rendering code would immediately re-add it to `selected_ids` -
    i.e. the checkbox would appear to "re-check itself" right after a bulk
    action. Removing the checkbox's own session_state entry forces it back
    to an unchecked default the next time it's drawn.
    """
    for loan_id in st.session_state.selected_ids:
        set_loan_review_state(loan_id, new_state)
        st.session_state.pop(f"chk_{loan_id}", None)
    st.session_state.selected_ids = set()


def _apply_workdesk_filters(
    df: pd.DataFrame, rule_filter: str, review_filter: str, search_text: str
) -> pd.DataFrame:
    """Apply the Rules / Review / Search filters and return the filtered DataFrame."""
    filtered = df

    if rule_filter == "Failed Compliance (All)":
        filtered = filtered[~filtered["overall_pass"]]
    elif rule_filter == "Rule 1: Min Value failures":
        filtered = filtered[~filtered["rule1_pass"]]
    elif rule_filter == "Rule 2: Currency failures":
        filtered = filtered[~filtered["rule2_pass"]]
    elif rule_filter == "Rule 3: Asset Coverage failures":
        filtered = filtered[~filtered["rule3_pass"]]
    # "All Loans (Pass + Fail)" -> no filtering needed.

    if review_filter != "All Review States":
        filtered = filtered[filtered["review_state"] == review_filter]

    if search_text:
        needle = search_text.strip().lower()
        filtered = filtered[
            filtered["loan_id"].str.lower().str.contains(needle)
            | filtered["company"].str.lower().str.contains(needle)
            | filtered["asset_type"].str.lower().str.contains(needle)
        ]

    return filtered


def _render_workdesk_toolbar() -> tuple[str, str, str, int]:
    """Render the search box + three filter dropdowns; return their current values."""
    # Same fix as the header: a fixed-ratio st.columns([3, 1.3, 1.3, 0.9]) row
    # doesn't wrap, so on a narrow window the search box and the three
    # dropdowns got squeezed instead of reflowing. A horizontal flex
    # container lets the search box stretch to fill the row on wide
    # screens, while the three dropdowns keep a fixed, readable width and
    # wrap onto their own line(s) when the window is too narrow for all
    # four to fit side by side.
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        search_text = st.text_input(
            "Search",
            placeholder="🔎  Search by Loan ID, Company Name, or Asset...",
            label_visibility="collapsed",
            key="search_box",
            width="stretch",
        )
        rule_filter = st.selectbox(
            "Rules", RULE_FILTER_OPTIONS, index=0, key="rule_filter", width=230
        )
        review_filter = st.selectbox(
            "Review", REVIEW_FILTER_OPTIONS, index=0, key="review_filter", width=210
        )
        rows_per_page = st.selectbox(
            "Rows", [25, 50, 100, 200], index=0, key="rows_per_page", width=100
        )
    return search_text, rule_filter, review_filter, rows_per_page


def _render_workdesk_status_bar(total_matches: int, failing_total: int, total_pages: int) -> None:
    """
    Render the "Showing N of M" status line and the page stepper on one
    stable row, plus - only when rows are checked - a second row of bulk
    action buttons underneath.

    This used to share a single 5-column row with the bulk-action buttons,
    which meant the page stepper sat alone on the far right with large
    empty gaps whenever nothing was selected (and jumped around whenever
    the selection count changed). Splitting it into "always visible" vs
    "only when something is selected" rows keeps the page control in a
    fixed, predictable place.
    """
    n_selected = len(st.session_state.selected_ids)

    status_col, page_col = st.columns([3, 1.1], vertical_alignment="center")
    with status_col:
        selected_note = f" &nbsp;•&nbsp; <strong>{n_selected}</strong> selected" if n_selected else ""
        st.markdown(
            f'<div class="wd-status-text">Showing {total_matches:,} of {failing_total:,} '
            f"flagged loans{selected_note}</div>",
            unsafe_allow_html=True,
        )
    with page_col:
        current_page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.page,
            step=1,
            label_visibility="collapsed",
            key="page_input",
        )
        st.session_state.page = current_page

    if n_selected:
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        bulk_remediate_col, bulk_ignore_col, bulk_remove_col, _spacer_col = st.columns([1.3, 1.0, 1.0, 2.7])
        with bulk_remediate_col:
            st.button(
                "✅ Remediate selected",
                use_container_width=True,
                key="bulk_remediate",
                on_click=_apply_bulk_action,
                args=("Remediated (AI/Manual)",),
            )
        with bulk_ignore_col:
            st.button(
                "🙈 Ignore",
                use_container_width=True,
                key="bulk_ignore",
                on_click=_apply_bulk_action,
                args=("Ignored",),
            )
        with bulk_remove_col:
            st.button(
                "🗑️ Remove",
                use_container_width=True,
                key="bulk_remove",
                on_click=_apply_bulk_action,
                args=("Removed",),
            )
        st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)


# Options shown in each failing row's single "Actions" dropdown. The first
# entry is a placeholder/prompt, not a real state - the dropdown always
# snaps back to it after applying a choice (see _on_row_action_change).
ACTION_PLACEHOLDER = "Review / Fix"
ACTION_REMEDIATE = "✅ Remediate"
ACTION_IGNORE = "🙈 Ignore"
ACTION_REMOVE = "🗑️ Remove"
ROW_ACTION_OPTIONS = [ACTION_PLACEHOLDER, ACTION_REMEDIATE, ACTION_IGNORE, ACTION_REMOVE]
ROW_ACTION_TO_REVIEW_STATE = {
    ACTION_REMEDIATE: "Remediated (AI/Manual)",
    ACTION_IGNORE: "Ignored",
    ACTION_REMOVE: "Removed",
}


def _on_row_action_change(loan_id: str, select_key: str) -> None:
    """
    Apply the action chosen in one row's Actions dropdown, then reset that
    dropdown back to its placeholder.

    Using `on_change` here (instead of a popover containing 3 separate
    buttons) cuts the Actions column from up to 4 Streamlit widgets per row
    down to a single selectbox - across a page of up to 200 rows, that is a
    large share of the app's total widget count, and was one of the
    biggest contributors to slow interactions in the Review Workdesk.

    The dropdown intentionally does NOT keep showing the chosen action -
    it resets to the placeholder immediately. The STATUS column's pill is
    the single source of truth for a loan's current review state; this
    control is a one-shot command menu, not a status display, which avoids
    the two ever getting out of sync (e.g. after a bulk action touches a
    row this dropdown was never opened for).
    """
    chosen_action = st.session_state[select_key]
    new_review_state = ROW_ACTION_TO_REVIEW_STATE.get(chosen_action)
    if new_review_state is not None:
        set_loan_review_state(loan_id, new_review_state)
    st.session_state[select_key] = ACTION_PLACEHOLDER


def _render_workdesk_row(row: pd.Series) -> None:
    """Render a single loan as one row of the Review Workdesk table."""
    row_cols = st.columns(WORKDESK_COLUMN_WEIGHTS, vertical_alignment="center")
    loan_id = row["loan_id"]

    # -- selection checkbox --------------------------------------------------
    # `selected_ids` is kept in sync with every "chk_*" checkbox by
    # _sync_selected_ids_from_checkboxes(), which runs earlier in
    # render_review_workdesk() - so this just needs to display the current
    # state; it doesn't need to update selected_ids itself.
    with row_cols[0]:
        is_checked = loan_id in st.session_state.selected_ids
        st.checkbox("Select loan", value=is_checked, key=f"chk_{loan_id}", label_visibility="collapsed")

    # -- status pill ----------------------------------------------------------
    with row_cols[1]:
        st.markdown(status_pill_html(row["review_state"]), unsafe_allow_html=True)

    # -- loan id ----------------------------------------------------------------
    with row_cols[2]:
        st.markdown(f'<div class="row-loanid">{loan_id}</div>', unsafe_allow_html=True)

    # -- company & HQ -------------------------------------------------------------
    with row_cols[3]:
        st.markdown(
            f'<div class="row-company">{row["company"]}</div>'
            f'<div class="row-country">{row["country"]}</div>',
            unsafe_allow_html=True,
        )

    # -- loan value (native currency + EUR-converted) -------------------------------
    with row_cols[4]:
        native_decimals = 0 if row["currency"] == "JPY" else 2
        st.markdown(
            f'<div class="row-primary">{fmt_number(row["loan_value"], native_decimals)} {row["currency"]}</div>'
            f'<div class="row-secondary">~{fmt_number(row["loan_value_eur"], 2)} EUR</div>',
            unsafe_allow_html=True,
        )

    # -- pledged asset (truncated label + native value) ------------------------------
    with row_cols[5]:
        asset_label = row["asset_type"]
        short_label = asset_label if len(asset_label) <= 42 else asset_label[:40] + "…"
        native_decimals = 0 if row["currency"] == "JPY" else 2
        st.markdown(
            f'<div class="row-asset" title="{asset_label}">{short_label}</div>'
            f'<div class="row-secondary">{fmt_number(row["asset_value"], native_decimals)} {row["currency"]}</div>',
            unsafe_allow_html=True,
        )

    # -- coverage % (green if it clears the rule, red if it fails) -------------------
    with row_cols[6]:
        coverage = row["coverage_pct"]
        coverage_css_class = "cov-green" if coverage >= MIN_COVERAGE_PCT else "cov-red"
        st.markdown(f'<span class="{coverage_css_class}">{coverage:.1f}%</span>', unsafe_allow_html=True)

    # -- R1 / R2 / R3 pass-fail badges --------------------------------------------------
    with row_cols[7]:
        st.markdown(
            rule_badge_html("R1", row["rule1_pass"])
            + rule_badge_html("R2", row["rule2_pass"])
            + rule_badge_html("R3", row["rule3_pass"]),
            unsafe_allow_html=True,
        )

    # -- actions: a single lightweight command dropdown (only for failing loans) -----
    with row_cols[8]:
        if row["overall_pass"]:
            st.markdown('<span class="row-secondary">— No action needed —</span>', unsafe_allow_html=True)
        else:
            select_key = f"action_{loan_id}"
            st.selectbox(
                "Action",
                ROW_ACTION_OPTIONS,
                key=select_key,
                label_visibility="collapsed",
                on_change=_on_row_action_change,
                args=(loan_id, select_key),
            )

    st.markdown('<div class="lcs-divider"></div>', unsafe_allow_html=True)


def _sync_selected_ids_from_checkboxes() -> None:
    """
    Reconcile `selected_ids` with the row checkboxes' own live values.

    Streamlit updates a widget's session_state value the moment it's
    interacted with - even before the callback/script body below it runs.
    `selected_ids` is *our* separate bookkeeping set, updated inside the row
    loop; without this sync, calling it before the row loop (which is where
    the status bar needs it, since the status bar is drawn above the
    table) would read one-rerun-stale data - e.g. checking a box wouldn't
    reveal the bulk-action bar until a second, unrelated rerun. Scanning the
    (small) set of "chk_*" keys already in session_state fixes that with
    negligible cost.
    """
    for key, is_checked in list(st.session_state.items()):
        if not key.startswith("chk_"):
            continue
        loan_id = key[len("chk_") :]
        if is_checked:
            st.session_state.selected_ids.add(loan_id)
        else:
            st.session_state.selected_ids.discard(loan_id)


def render_review_workdesk(df: pd.DataFrame) -> None:
    """Render the full Review Workdesk tab: toolbar, bulk actions, and table."""
    failing_total = int((~df["overall_pass"]).sum())

    search_text, rule_filter, review_filter, rows_per_page = _render_workdesk_toolbar()
    filtered_df = _apply_workdesk_filters(df, rule_filter, review_filter, search_text)

    total_matches = len(filtered_df)
    total_pages = max(1, (total_matches - 1) // rows_per_page + 1) if total_matches else 1
    st.session_state.page = min(st.session_state.page, total_pages)

    _sync_selected_ids_from_checkboxes()
    _render_workdesk_status_bar(total_matches, failing_total, total_pages)

    page_start = (st.session_state.page - 1) * rows_per_page
    page_df = filtered_df.iloc[page_start : page_start + rows_per_page]

    # -- table header row ---------------------------------------------------
    header_cols = st.columns(WORKDESK_COLUMN_WEIGHTS)
    for col, header_text in zip(header_cols, WORKDESK_COLUMN_HEADERS):
        col.markdown(f'<div class="lcs-col-header">{header_text}</div>', unsafe_allow_html=True)

    if page_df.empty:
        st.info("No loans match the current filters.")
        return

    for _, row in page_df.iterrows():
        _render_workdesk_row(row)

    st.caption(f"Page {st.session_state.page} of {total_pages}")


# =============================================================================
# 12. TAB 2: COMPLIANCE & PORTFOLIO REPORT
#     Portfolio-wide metric cards + a failures-by-rule bar chart and a
#     remediation-progress donut chart.
# =============================================================================
def _render_report_metric_cards(df: pd.DataFrame) -> tuple:
    """Render the four metric cards + the export button; return the raw
    numbers so the charts below can reuse them without recomputing."""
    total = len(df)
    passed = int(df["overall_pass"].sum())
    failing_mask = ~df["overall_pass"]
    unresolved_failures = int((failing_mask & (df["review_state"] == "Unreviewed")).sum())
    remediated = int((df["review_state"] == "Remediated (AI/Manual)").sum())
    ignored = int((df["review_state"] == "Ignored").sum())
    removed = int((df["review_state"] == "Removed").sum())

    pass_rate_pct = passed / total * 100 if total else 0.0
    portfolio_value_eur = df["loan_value_eur"].sum()

    card_cols = st.columns([1, 1, 1, 1, 0.9])
    with card_cols[0]:
        st.markdown(
            f"""<div class="card">
                  <div class="card-label">Total Portfolio Value <span>💰</span></div>
                  <div class="card-value green">{fmt_eur_millions(portfolio_value_eur)}</div>
                  <div class="card-sub">Total EUR converted value</div>
                </div>""",
            unsafe_allow_html=True,
        )
    with card_cols[1]:
        st.markdown(
            f"""<div class="card">
                  <div class="card-label">Overall Pass Rate <span>🛡️</span></div>
                  <div class="card-value green">{pass_rate_pct:.1f}%</div>
                  <div class="card-sub">{passed:,} loans passed OPA Rego</div>
                </div>""",
            unsafe_allow_html=True,
        )
    with card_cols[2]:
        st.markdown(
            f"""<div class="card">
                  <div class="card-label">Total Compliance Failures <span>⚠️</span></div>
                  <div class="card-value red">{unresolved_failures:,}</div>
                  <div class="card-sub">{unresolved_failures / total * 100:.1f}% of total loans</div>
                </div>""",
            unsafe_allow_html=True,
        )
    with card_cols[3]:
        st.markdown(
            f"""<div class="card">
                  <div class="card-label">Remediated &amp; Fixed <span>✅</span></div>
                  <div class="card-value indigo">{remediated:,}</div>
                  <div class="card-sub">Fixed via AI Suggestions or Manual</div>
                </div>""",
            unsafe_allow_html=True,
        )
    with card_cols[4]:
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        st.download_button(
            "📄 Export Full Audit Report CSV",
            data=dataframe_to_csv_bytes(df),
            file_name=f"loan_compliance_full_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
            key="export_report_btn",
        )

    return total, passed, unresolved_failures, remediated, ignored, removed


def _build_failures_by_rule_figure(df: pd.DataFrame) -> go.Figure:
    """Build the 'Failures Breakdown by Compliance Rule' bar chart."""
    rule1_fail_count = int((~df["rule1_pass"]).sum())
    rule2_fail_count = int((~df["rule2_pass"]).sum())
    rule3_fail_count = int((~df["rule3_pass"]).sum())
    counts = [rule1_fail_count, rule2_fail_count, rule3_fail_count]

    figure = go.Figure(
        data=[
            go.Bar(
                x=["Rule 1: Min Value", "Rule 2: Currency", "Rule 3: Asset Coverage"],
                y=counts,
                marker_color=[COLORS["red"], COLORS["purple"], COLORS["blue"]],
                text=[f"{count:,}" for count in counts],
                textposition="outside",
                textfont=dict(color=COLORS["text_primary"]),
                width=0.5,
            )
        ]
    )
    figure.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text_secondary"]),
        margin=dict(l=10, r=10, t=30, b=10),
        height=380,
        xaxis=dict(showgrid=False, color=COLORS["text_secondary"]),
        yaxis=dict(showgrid=True, gridcolor=COLORS["card_border"], color=COLORS["text_secondary"]),
        showlegend=False,
    )
    return figure


def _build_remediation_donut_figure(passed, ignored, remediated, removed, unresolved_failures):
    """Build the 'Remediation Progress & Audit Status' donut chart, plus its
    labels/colours (returned so the legend below can reuse them)."""
    labels = ["Clean / Passed", "Ignored", "Remediated (AI/Manual)", "Removed", "Unreviewed Failing"]
    values = [passed, ignored, remediated, removed, unresolved_failures]
    colors = [COLORS["green"], COLORS["grey"], COLORS["purple"], COLORS["red"], COLORS["orange"]]

    figure = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.68,
                marker=dict(colors=colors, line=dict(color=COLORS["card_bg"], width=2)),
                textinfo="none",
                sort=False,
            )
        ]
    )
    figure.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=20, b=10),
        height=340,
        showlegend=False,
    )
    return figure, labels, colors


def render_compliance_report(df: pd.DataFrame) -> None:
    """Render the full Compliance & Portfolio Report tab."""
    total = len(df)

    st.markdown(
        f"""
        <div class="section-card" style="margin-bottom:16px;">
          <div class="section-title">Compliance &amp; Portfolio Audit Report</div>
          <div class="section-sub">Comprehensive compliance breakdown across {total:,} total portfolio loans</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, passed, unresolved_failures, remediated, ignored, removed = _render_report_metric_cards(df)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    left_col, right_col = st.columns([1.15, 1])

    with left_col:
        st.markdown('<div class="section-card" style="height:100%;">', unsafe_allow_html=True)
        st.markdown(
            '<div class="panel-title">⚠️ Failures Breakdown by Compliance Rule</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="panel-sub">Individual rule failure counts across all audited loans</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            _build_failures_by_rule_figure(df), use_container_width=True, config={"displayModeBar": False}
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        st.markdown('<div class="section-card" style="height:100%;">', unsafe_allow_html=True)
        st.markdown(
            '<div class="panel-title">✅ Remediation Progress &amp; Audit Status</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="panel-sub">Distribution of audit outcomes across all compliance exceptions</div>',
            unsafe_allow_html=True,
        )

        donut_figure, legend_labels, legend_colors = _build_remediation_donut_figure(
            passed, ignored, remediated, removed, unresolved_failures
        )
        st.plotly_chart(donut_figure, use_container_width=True, config={"displayModeBar": False})

        legend_item_template = (
            "<div style='display:flex; align-items:center; gap:6px; "
            f"font-size:12.5px; color:{COLORS['text_secondary']};'>"
            "<span style='width:10px; height:10px; border-radius:3px; "
            "background:{color}; display:inline-block;'></span>{label}</div>"
        )
        legend_items = "".join(
            legend_item_template.format(color=color, label=label)
            for label, color in zip(legend_labels, legend_colors)
        )
        legend_wrapper = (
            "<div style='display:flex; flex-wrap:wrap; gap:14px; "
            f"justify-content:center; margin-top:-10px;'>{legend_items}</div>"
        )
        st.markdown(legend_wrapper, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# 13. TAB 3: OPA REGO PLAYGROUND (illustrative demo, not a real OPA engine)
# =============================================================================
SAMPLE_REGO_POLICY = """package loan.compliance

# Rule 1 - Min Value: pledged collateral must clear the floor value
rule1_min_value {
    input.loan.asset_value_eur >= data.thresholds.min_asset_value_eur
}

# Rule 2 - Currency: loan must be denominated in an approved settlement currency
rule2_currency {
    input.loan.currency == data.approved_currencies[_]
}

# Rule 3 - Asset Coverage: collateral must cover a minimum % of loan value
rule3_asset_coverage {
    coverage := (input.loan.asset_value_eur / input.loan.loan_value_eur) * 100
    coverage >= data.thresholds.min_coverage_pct
}

allow {
    rule1_min_value
    rule2_currency
    rule3_asset_coverage
}
"""


def render_opa_playground(df: pd.DataFrame) -> None:
    """
    Render a simulated OPA Rego sandbox.

    NOTE: this does NOT call a real OPA (Open Policy Agent) engine - it is a
    lightweight illustration that checks whether each rule's function name
    is present in the text box, then shows that rule's already-computed
    pass/fail result for the chosen sample loan. Swap in a real OPA client
    (e.g. the `opa` CLI via subprocess, or an HTTP call to an OPA server)
    if you want genuine policy evaluation.
    """
    st.markdown(
        """
        <div class="section-card">
          <div class="section-title">OPA Rego Playground</div>
          <div class="section-sub">Simulated policy sandbox — edit the policy and test it against a
          sample loan from the current portfolio. This is an illustrative evaluator, not a real OPA engine.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    editor_col, test_col = st.columns([1.3, 1])

    with editor_col:
        policy_text = st.text_area("Policy (Rego)", value=SAMPLE_REGO_POLICY, height=380, key="rego_policy")

    with test_col:
        st.markdown("**Test input — sample loan**")
        sample_loan_ids = df["loan_id"].sample(min(25, len(df)), random_state=1).tolist()
        chosen_loan_id = st.selectbox("Pick a loan to test", sample_loan_ids, key="rego_sample_loan")
        loan_row = df[df["loan_id"] == chosen_loan_id].iloc[0]

        st.json(
            {
                "loan": {
                    "loan_id": loan_row["loan_id"],
                    "currency": loan_row["currency"],
                    "loan_value_eur": loan_row["loan_value_eur"],
                    "asset_value_eur": loan_row["asset_value_eur"],
                }
            }
        )

        if st.button("▶️ Evaluate policy", type="primary", key="eval_rego"):
            rule1_present = "rule1_min_value" in policy_text
            rule2_present = "rule2_currency" in policy_text
            rule3_present = "rule3_asset_coverage" in policy_text

            st.markdown("**Evaluation result:**")
            st.markdown(
                rule_badge_html("R1 Min Value", bool(loan_row["rule1_pass"]) if rule1_present else True),
                unsafe_allow_html=True,
            )
            st.markdown(
                rule_badge_html("R2 Currency", bool(loan_row["rule2_pass"]) if rule2_present else True),
                unsafe_allow_html=True,
            )
            st.markdown(
                rule_badge_html("R3 Asset Coverage", bool(loan_row["rule3_pass"]) if rule3_present else True),
                unsafe_allow_html=True,
            )

            if bool(loan_row["overall_pass"]):
                st.success("allow = true")
            else:
                st.error("allow = false")


# =============================================================================
# 14. TAB 4: ASSET VALUE PREDICTOR (heuristic demo, NOT a trained ML model)
# =============================================================================
def render_asset_predictor(df: pd.DataFrame) -> None:
    """
    Render a lightweight heuristic 'predictor'.

    NOTE: this is NOT a trained machine-learning model. It estimates a
    plausible asset value from the average collateral-coverage ratio seen
    for similar assets in the current portfolio, plus a small amount of
    random noise for variety. Swap this out for a real model (e.g. a
    scikit-learn/XGBoost regressor trained on historical appraisals) when
    you have labelled training data.
    """
    st.markdown(
        """
        <div class="section-card">
          <div class="section-title">Asset Value Predictor (ML)</div>
          <div class="section-sub">Heuristic estimator based on portfolio statistics — enter asset details to get
          a rough fair-value estimate. Demo only, not a production model.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    input_col, result_col = st.columns([1, 1.2])

    with input_col:
        asset_type = st.selectbox("Asset type", DEMO_ASSET_TYPES, key="pred_asset_type")
        country = st.selectbox("Jurisdiction", DEMO_COUNTRIES, key="pred_country")
        loan_value_eur = st.slider(
            "Associated loan value (EUR)", 5_000, 20_000_000, 500_000, step=5_000, key="pred_loan_value"
        )
        run_prediction = st.button("🔮 Predict asset value", type="primary", key="predict_btn")

    with result_col:
        comparable_loans = df[df["asset_type"] == asset_type]
        avg_coverage_pct = (
            comparable_loans["coverage_pct"].mean() if len(comparable_loans) else df["coverage_pct"].mean()
        )
        if run_prediction:
            # A small deterministic "noise" term so repeated predictions for
            # the same inputs are stable, but different inputs vary a bit.
            noise_factor = np.random.default_rng(hash(asset_type + country) % (2**32)).normal(1.0, 0.05)
            predicted_value_eur = loan_value_eur * (avg_coverage_pct / 100.0) * noise_factor

            st.metric("Predicted asset value", f"€{predicted_value_eur:,.0f}")
            st.caption(
                f"Based on {len(comparable_loans):,} comparable loans secured by similar assets "
                f"(avg. coverage {avg_coverage_pct:.1f}%)."
            )
            confidence_pct = min(95, 60 + len(comparable_loans) / 500)
            st.progress(confidence_pct / 100, text=f"Model confidence: {confidence_pct:.0f}%")
        else:
            st.info("Set the parameters and click **Predict asset value**.")


# =============================================================================
# 15. MAIN ENTRY POINT
# =============================================================================
# Static nav labels (no dynamic counts baked into the text). Keeping these
# fixed means the segmented control's selected value stays stable across
# reruns even as portfolio numbers change - see the docstring on main().
NAV_REVIEW_WORKDESK = "⚙️ Review Workdesk"
NAV_COMPLIANCE_REPORT = "📊 Compliance & Portfolio Report"
NAV_OPA_PLAYGROUND = "📄 OPA Rego Playground"
NAV_ASSET_PREDICTOR = "🧠 Asset Value Predictor (ML)"
NAV_OPTIONS = [NAV_REVIEW_WORKDESK, NAV_COMPLIANCE_REPORT, NAV_OPA_PLAYGROUND, NAV_ASSET_PREDICTOR]


def main() -> None:
    """
    Wire everything together: theme, state, data, header, and navigation.

    PERFORMANCE NOTE: this deliberately does NOT use st.tabs(). st.tabs()
    runs the code inside every tab on every single rerun and only *hides*
    the inactive ones with CSS - so with a 100,000-row table, two Plotly
    charts, and several other widgets, every click anywhere in the app was
    silently rebuilding all of them. st.segmented_control() is used here as
    a lightweight "which section is active" switch instead, and the
    if/elif below calls ONLY the matching render_*() function - this is
    what fixed the interaction latency.

    COMPATIBILITY NOTE: we deliberately do NOT pass required=True to
    st.segmented_control(). That parameter only exists in very recent
    Streamlit releases - older (but still perfectly current) installs raise
    `TypeError: segmented_control() got an unexpected keyword argument
    'required'`. Without it, clicking the already-active segment again
    de-selects it and returns None instead of always keeping one selected.
    We handle that ourselves below with `last_active_section`, which works
    on any Streamlit version that has st.segmented_control() at all.
    """
    inject_css()
    init_session_state()
    portfolio_df = get_portfolio_data()

    render_header(portfolio_df)

    st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)
    active_section = st.segmented_control(
        "Section",
        options=NAV_OPTIONS,
        default=NAV_REVIEW_WORKDESK,
        key="active_section",
        label_visibility="collapsed",
    )
    # segmented_control() returns None if the active segment was clicked
    # again (de-selecting it) - fall back to whichever section was active
    # before that happened, so the view never goes blank.
    if active_section is not None:
        st.session_state.last_active_section = active_section
    active_section = st.session_state.last_active_section
    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    if active_section == NAV_REVIEW_WORKDESK:
        render_review_workdesk(portfolio_df)
    elif active_section == NAV_COMPLIANCE_REPORT:
        render_compliance_report(portfolio_df)
    elif active_section == NAV_OPA_PLAYGROUND:
        render_opa_playground(portfolio_df)
    else:
        render_asset_predictor(portfolio_df)


if __name__ == "__main__":
    main()
