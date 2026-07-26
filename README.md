# Payments Reconciliation Tool (Assessment)

## What this includes 
- Synthetic March 2025 platform and settlement datasets generated in code.
- Four intentionally planted gap types:
  - late settlement into next month
  - aggregate rounding drift
  - duplicate transaction entry
  - orphan refund with no original platform transaction
- Reconciliation logic with labeled mismatch reasons.
- Streamlit dashboard for summary and mismatch breakdown.
- Pytest suite with one test per planted gap type.

## One-command local setup and run
Run this from the project root:

```bash
pip install -r requirements.txt && streamlit run app.py
```

## Run tests
```bash
pytest -q
```

## Deploy free on Streamlit Community Cloud
1. Push this project to a public GitHub repository.
2. Go to https://streamlit.io/cloud and sign in with GitHub.
3. Click New app and select your repository, branch, and app.py as the entrypoint.
4. Deploy the app to get a public URL you can share.
