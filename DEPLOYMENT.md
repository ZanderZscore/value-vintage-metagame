# GitHub + Streamlit Community Cloud deployment

This project is ready for:

1. GitHub hosting
2. weekly data refreshes with GitHub Actions
3. Streamlit Community Cloud deployment

## 1. Push the repository to GitHub

From the project directory:

```bash
git init
git add .
git commit -m "Initial Value Vintage metagame app"
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

You can use an HTTPS remote instead of SSH if preferred.

## 2. GitHub Actions permissions

The workflow uses:

```yaml
permissions:
  contents: write
```

If the automatic commit is rejected, check:

**Repository → Settings → Actions → General → Workflow permissions**

and allow **Read and write permissions**.

If `main` is protected and requires pull requests, either allow GitHub Actions
to bypass that rule or adapt the workflow to open a PR instead of pushing
directly.

## 3. Weekly refresh

The workflow file is:

```text
.github/workflows/update-metagame.yml
```

It runs every Monday at **6:00 AM America/Chicago**.

It executes:

```bash
python build_data.py --days 90
```

then:

1. validates the generated data;
2. prints a short summary to the Actions log;
3. commits changed generated files;
4. pushes the commit to the repository.

The workflow also supports a manual run:

**GitHub → Actions → Update Value Vintage metagame → Run workflow**

There is an optional checkbox to force-refresh every cached Moxfield deck.

## 4. Moxfield token, if needed

Try the workflow without a token first.

If Moxfield returns HTTP 401/403:

**Repository → Settings → Secrets and variables → Actions → New repository secret**

Create:

```text
MOXFIELD_BEARER_TOKEN
```

The workflow already passes that secret only to the build step.

Do not commit the token into the repository.

## 5. Cache behavior

These are deliberately NOT committed:

```text
data/decklists_raw/
data/card_cache.json
```

GitHub Actions stores/restores them with `actions/cache`, which avoids
redownloading every historical Moxfield list each week while keeping the repo
smaller.

The app-ready generated files ARE committed:

```text
app_data/
data/vv_online_results.csv
data/decks_normalized.json
data/deck_cards.csv
data/deck_fetch_failures.csv
data/clustering/
```

## 6. Streamlit Community Cloud

In Streamlit Community Cloud:

1. Create a new app.
2. Select this GitHub repository.
3. Select branch `main`.
4. Set the app file to:

```text
app.py
```

5. Deploy.

Streamlit will install `requirements.txt` and run `app.py`.

Because `app_data/` is committed, the deployed app does not need to crawl VV
or Moxfield during startup.

When the Monday GitHub Action commits new `app_data/`, Streamlit Community
Cloud sees the repository change and refreshes the app.

## 7. Manual refresh flow

You can refresh the site without touching your local machine:

```text
GitHub
  → Actions
  → Update Value Vintage metagame
  → Run workflow
```

After the workflow commits the refreshed data, Streamlit picks it up.

## 8. Failure behavior

The workflow validates generated data before committing.

If scraping, Moxfield access, normalization, clustering, or validation fails,
the workflow fails before the commit step. The repository therefore retains
the previous known-good `app_data/`, and the deployed Streamlit app continues
using that data.
