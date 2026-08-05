# BIL-red-pandas

# Loan Compliance System (Streamlit)

A Streamlit recreation of the **Loan Compliance System** dashboard — a
"Deterministic Rule Enforcement & Agentic Remediation" demo covering:

1. **Review Workdesk** — searchable/filterable table of loans that failed
   compliance, with checkboxes for bulk actions and a per-row Actions
   dropdown (Remediate, Ignore, Remove).
2. **Compliance & Portfolio Report** — portfolio-wide metric cards, a
   failures-by-rule bar chart, and a remediation-progress donut chart.
3. Two lighter bonus sections: an **OPA Rego Playground** (simulated policy
   evaluator) and an **Asset Value Predictor (ML)** (heuristic demo
   estimator).

Navigation between the four sections uses `st.segmented_control()`, not
`st.tabs()` — see the Changelog below for why that matters for performance.

Theme: light (white cards on a soft grey-blue background). All colours are
defined once in the `COLORS` dict near the top of `app.py` if you want to
re-theme. `.streamlit/config.toml` mirrors the same accent colour for
Streamlit's own native widgets (checkboxes, sliders, segmented control) -
keep that file alongside `app.py`.

If you're not a developer and just want to run this once to see it, use
**`Loan_Compliance_System_Setup_Guide.docx`** instead of this file — it's a
plain-language, step-by-step walkthrough for Visual Studio Code.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501).

## Code layout (`app.py`)

The file is organised into numbered sections, top to bottom:

1. Page config
2. **Data source switch** (`DATA_SOURCE_MODE`) — see below
3. Domain constants (FX rates, rule thresholds, demo vocabulary)
4. Colour palette (`COLORS`)
5. CSS theme injection
6. Synthetic demo data generator (`generate_demo_loans`)
7. **Data source adapters** — see below
8. Formatting/HTML helper functions
9. Session state
10. Header
11. Review Workdesk
12. Compliance & Portfolio Report
13. OPA Rego Playground (illustrative only)
14. Asset Value Predictor (heuristic only, not a trained model)
15. `main()` — the lazy-nav switch; see the Changelog below

## Connecting your own data

Everything defaults to a synthetic 100,000-loan demo portfolio
(`generate_demo_loans`, cached with `@st.cache_data`) so the app runs with
zero configuration. To use real data, change `DATA_SOURCE_MODE` near the top
of `app.py`:

```python
DATA_SOURCE_MODE = "demo"    # default — synthetic data, no setup needed
DATA_SOURCE_MODE = "csv"     # load CSV_DATA_PATH via load_data_from_csv()
DATA_SOURCE_MODE = "custom"  # calls load_data_from_custom_source() — your code
```

Search `app.py` for **"DATA SOURCE ADAPTERS"** for the full picture. There
are four adapter functions, each documented with the exact DataFrame schema
every adapter must return:

| Function | Status | Purpose |
|---|---|---|
| `load_data_from_csv(csv_path)` | Works as-is | Load a CSV matching `EXPORT_COLUMNS`. |
| `load_data_from_pdf_vectors(pdf_folder_path)` | Placeholder — raises `NotImplementedError` | Extract structured loan records from PDFs via a vector store. |
| `load_data_from_llm_extraction(source_texts)` | Placeholder — raises `NotImplementedError` | Use an LLM to pull structured fields out of free text. |
| `load_data_from_custom_source()` | Placeholder — raises `NotImplementedError` | Single entry point to combine any of the above (or a live DB/API call). |

Every adapter must return a `pandas.DataFrame` with the columns listed in
`EXPORT_COLUMNS` (also documented inline above each adapter). If your source
data doesn't already include the three rule-pass booleans, compute them the
same way `generate_demo_loans()` does — that block is intentionally kept
simple and copy-pasteable.

## Code quality

This file has been run through:

```bash
pip install black flake8
black --line-length 110 app.py       # formatting
flake8 app.py                        # lint (config in .flake8)
```

Both currently pass clean. `.flake8` documents why the line-length limit is
slightly above the PEP 8 default (the file embeds CSS/HTML as Python
strings, and breaking those mid-rule hurts readability for no real benefit).

## Notes

- FX rates are static demo values (`FX_RATES` in `app.py`) — swap in a live
  FX API call if you need real-time conversion.
- The OPA Rego Playground does **not** call a real OPA engine — it's an
  illustrative check against the policy text, clearly labelled as such in
  both the UI and the code's docstrings.
- The Asset Value Predictor is a heuristic over the generated/loaded data,
  **not** a trained ML model — also labelled as such.
- Remediated/Failures counters are live: resolving exceptions in the
  Workdesk updates the header and report tab immediately, while "Overall
  Pass Rate" stays fixed (it reflects the deterministic rule verdict, not
  remediation state).


Step 1: Start the OPA Server
Open a terminal window and spin up the Open Policy Agent container, mounting your local Rego compliance policies:

# Navigate to your policy directory or run OPA via Docker
docker run -d --name opa -p 8181:8181 openpolicyagent/opa:latest run --server --set=decision_logs.console=true

To load your specific compliance rules into OPA, ensure your compliance.rego is active or pushed to OPA's data endpoint : 

curl -X PUT --data-binary @compliance.rego http://localhost:8181/v1/policies/loan_compliance

Test with test payload : 

curl -X POST http://localhost:8181/v1/data/loan/compliance -H "Content-Type: application/json" -d '{
  "input": {
    "LoanID": "TEST-001",
    "LoanValueEUR": 20000.00
  }
}'

