# Implementation Guide — Rolling Out the Production Architecture

> Companion to [docs/production-architecture.md](production-architecture.md) (the *what and why*) and [infra/README.md](../infra/README.md) (the *Terraform reference*). This document is the *how*: an ordered, step-by-step runbook for actually standing this system up, from an empty Azure subscription to a live `prod` deployment.
>
> **Status**: plan approved by PM. Nothing in this guide has been executed yet — treat every command below as the next action to take, not something already done.
>
> **Explicitly deferred** (per team decision, revisit later, not part of this rollout): fixing the two silent-drop bugs in `pipeline/main.go` (missing FX rate / OPA call failures dropping loans with no log) and adding real automated test coverage (`go test`, `opa test`, `pytest`). Phase 1 below flags where these gaps affect what you're deploying, but does not fix them.

---

## How to use this document

Work through the phases **in order** — each one assumes the previous is done and verified. Every phase ends with a **✅ Definition of done** checklist; don't move to the next phase until every box is checked. Commands assume you're in the repo root unless a `cd` is shown.

---

## Phase 0 — Prerequisites and access

### 0.1 Tools

Install locally (or confirm already installed):

```bash
brew install terraform azure-cli gh
terraform -version   # >= 1.7.0
az version
gh --version
```

### 0.2 Accounts and access needed before starting

| What | Who provides it | Used for |
|---|---|---|
| Azure subscription (dev, staging, prod — can start as one subscription with 3 resource groups) | Whoever owns the Azure billing relationship | Everything |
| Owner/Contributor rights on that subscription (temporarily, for bootstrap only) | Azure subscription owner | Creating the resource groups, OIDC app registration, and remote state storage account |
| GitHub repo admin rights on the target repo | Repo owner | Creating GitHub Environments (`dev`, `staging`, `prod`), secrets, and variables |
| A Microsoft Entra ID tenant (can be the same tenant as the Azure subscription) | Same as Azure subscription owner | Easy Auth / SSO in Phase 4 |

### 0.3 Log in

```bash
az login
az account set --subscription "<your-subscription-id>"
gh auth login   # if not already authenticated
```

### ✅ Definition of done
- [ ] `az account show` returns the correct subscription
- [ ] `terraform -version` ≥ 1.7.0
- [ ] You have Owner or Contributor on the subscription
- [ ] You have admin on the GitHub repo

---

## Phase 1 — Bootstrap (one-time, manual, out-of-band)

Terraform cannot create the backend it stores its own state in, and CI/CD cannot authenticate to Azure until an identity exists — so these two things are created manually, once, before any `terraform init` will work.

### 1.1 Create the remote state storage account

```bash
az group create --name rg-tfstate-shared --location eastus

az storage account create \
  --name sttfstateloancompl \
  --resource-group rg-tfstate-shared \
  --sku Standard_RAGRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

az storage container create \
  --account-name sttfstateloancompl \
  --name tfstate \
  --auth-mode login

az storage account blob-service-properties update \
  --account-name sttfstateloancompl \
  --enable-versioning true
```

*(Full rationale for this step is in [infra/README.md](../infra/README.md#bootstrapping-remote-state-one-time-out-of-band).)*

### 1.2 Create the GitHub Actions OIDC app registration

This is the identity GitHub Actions uses to talk to Azure — **no client secret is ever created or stored**.

```bash
APP_ID=$(az ad app create --display-name "gh-actions-loancompl" --query appId -o tsv)
OBJECT_ID=$(az ad app show --id "$APP_ID" --query id -o tsv)
az ad sp create --id "$APP_ID"

# One federated credential per trigger you need OIDC for:
az ad app federated-credential create --id "$OBJECT_ID" --parameters '{
  "name": "gh-actions-main-push",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<org>/<repo>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

az ad app federated-credential create --id "$OBJECT_ID" --parameters '{
  "name": "gh-actions-pull-request",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<org>/<repo>:pull_request",
  "audiences": ["api://AzureADTokenExchange"]
}'

# One per GitHub Environment used by workflow_dispatch (promote.yml):
for ENV in dev staging prod; do
az ad app federated-credential create --id "$OBJECT_ID" --parameters "{
  \"name\": \"gh-actions-env-$ENV\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:<org>/<repo>:environment:$ENV\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}"
done
```

Grant least-privilege roles (resource-group scoped, not subscription-wide — the resource groups won't exist yet on the very first run, so grant at subscription scope initially and **tighten to resource-group scope after Phase 2's first `terraform apply` creates them**):

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az role assignment create --assignee "$APP_ID" --role "Contributor" --scope "/subscriptions/$SUBSCRIPTION_ID"
az role assignment create --assignee "$APP_ID" --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-tfstate-shared/providers/Microsoft.Storage/storageAccounts/sttfstateloancompl"
```

Record these three values — you'll need them for GitHub secrets in step 1.4:

```bash
echo "AZURE_CLIENT_ID=$APP_ID"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
```

### 1.3 Create GitHub Environments

In the repo: **Settings → Environments** → create `dev`, `staging`, `prod`.

- `dev`: no required reviewers (auto-deploy on merge).
- `staging`: 1 required reviewer.
- `prod`: 2 required reviewers, and (recommended) restrict to the `main` branch only.

### 1.4 Set GitHub secrets and variables

Repository-level (available to all workflows) or per-Environment (scope secrets that differ per environment, like `POSTGRES_ADMIN_PASSWORD`, to that Environment instead of the repo):

```bash
gh secret set AZURE_CLIENT_ID --body "<APP_ID from 1.2>"
gh secret set AZURE_TENANT_ID --body "<tenant id from 1.2>"
gh secret set AZURE_SUBSCRIPTION_ID --body "<subscription id from 1.2>"

# Per-environment secret (repeat for staging, prod with different strong passwords):
gh secret set POSTGRES_ADMIN_PASSWORD --env dev --body "<generate a strong password>"

# Variables read by infra-ci.yml / app-ci.yml (not secret, just config):
gh variable set ACR_NAME --body "acrloancompldev"          # must match infra/modules/acr naming per env
gh variable set ACR_LOGIN_SERVER --body "acrloancompldev.azurecr.io"
```

> ⚠️ Generate `POSTGRES_ADMIN_PASSWORD` with a password manager or `openssl rand -base64 24` — never reuse a password across dev/staging/prod.

### ✅ Definition of done
- [ ] `sttfstateloancompl` storage account + `tfstate` container exist, versioning enabled
- [ ] OIDC app registration created with federated credentials for `main`, `pull_request`, and each of `dev`/`staging`/`prod` environments
- [ ] GitHub Environments `dev`/`staging`/`prod` exist with correct reviewer rules
- [ ] `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` secrets set
- [ ] `POSTGRES_ADMIN_PASSWORD` set per environment
- [ ] `ACR_NAME` / `ACR_LOGIN_SERVER` variables set

---

## Phase 2 — First Terraform apply (dev only, run locally before trusting CI)

Do the very first apply **locally**, not through CI, so you can watch it closely and catch naming/quota issues interactively.

```bash
cd infra/environments/dev
terraform init
```

Review naming: `infra/modules/acr/main.tf` and the ACR name you set as a GitHub variable in 1.4 must match. Storage account names must be globally unique — if `sttfstateloancompl` or the ACR name is taken, change it now in both Terraform and the GitHub variable before proceeding.

```bash
terraform plan \
  -var="ui_image=mcr.microsoft.com/hello-world" \
  -var="api_image=mcr.microsoft.com/hello-world" \
  -var="pipeline_image=mcr.microsoft.com/hello-world" \
  -var="postgres_admin_password=<the dev password from 1.4>"
```

*(Placeholder public images on purpose — your real images don't exist in ACR yet; Phase 3 replaces them.)*

Read the plan output line by line. Confirm:
- Resource count and types match what you expect (networking, Key Vault, storage, ACR, PostgreSQL, monitoring, Container Apps — see [infra/README.md](../infra/README.md) layout).
- No resource is being destroyed (there shouldn't be anything to destroy on a first apply).

If it looks right:

```bash
terraform apply \
  -var="ui_image=mcr.microsoft.com/hello-world" \
  -var="api_image=mcr.microsoft.com/hello-world" \
  -var="pipeline_image=mcr.microsoft.com/hello-world" \
  -var="postgres_admin_password=<the dev password from 1.4>"
```

This takes several minutes (PostgreSQL Flexible Server provisioning is the slowest part). When it finishes:

```bash
terraform output
```

Confirm you get back `ui_fqdn`, `postgres_fqdn`, `acr_login_server`, `key_vault_uri`.

Now go back to Phase 1.2 and **tighten the OIDC app registration's role assignment** from subscription-scoped to just the two resource groups that now exist (`rg-loancompl-dev` and `rg-tfstate-shared`):

```bash
az role assignment delete --assignee "$APP_ID" --role "Contributor" --scope "/subscriptions/$SUBSCRIPTION_ID"
az role assignment create --assignee "$APP_ID" --role "Contributor" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-loancompl-dev"
```

### ✅ Definition of done
- [ ] `terraform apply` succeeded in `infra/environments/dev` with no errors
- [ ] All 4 outputs return real values
- [ ] Azure Portal shows `rg-loancompl-dev` populated with the expected resources
- [ ] OIDC role assignment tightened to resource-group scope

---

## Phase 3 — Wire up application CI/CD and get real images into ACR

### 3.1 Push to a branch and open a PR

With everything from Phase 1-2 in place, [.github/workflows/app-ci.yml](../.github/workflows/app-ci.yml) and [.github/workflows/infra-ci.yml](../.github/workflows/infra-ci.yml) can now actually run. Open a small PR (e.g. touch a comment in `pipeline/main.go`) and confirm:

- `app-ci.yml`'s `test` and `build-and-scan` jobs run and pass (or fail loudly and legitimately — see the note on empty test suites below).
- `infra-ci.yml`'s `plan` job runs for `dev`/`staging`/`prod` and posts a plan as a PR comment. **Expect the `staging`/`prod` plans to fail at `terraform init`** until you repeat Phase 2's backend/state bootstrap for those environments too (see Phase 6) — that's expected at this point, not a bug.

> Reminder: since automated tests are a deferred item, `go test ./...` / `pytest` currently pass trivially with **zero tests found** — the pipeline isn't lying to you, there's just nothing to fail yet. Don't mistake a green check here for verified correctness.

### 3.2 Merge to `main` and watch the dev auto-deploy

On merge, `app-ci.yml`'s `push` and `deploy-dev` jobs should:
1. Build and push real images to ACR tagged with the commit SHA.
2. Run `az containerapp update` against `ca-ui-dev` / `ca-suggestion-api-dev` and `az containerapp job update` against `caj-pipeline-dev`.
3. Smoke-test `/health` on the Suggestion API.

`infra-ci.yml`'s `apply-dev` job should also run `terraform apply -var="ui_image=...:dev-latest" ...` — pinning `dev` to the `:dev-latest` tag pattern.

### 3.3 Manually verify the real deployment

```bash
UI_FQDN=$(cd infra/environments/dev && terraform output -raw ui_fqdn)
curl -I "https://$UI_FQDN"
```

Open it in a browser. You should see the real Streamlit UI, not the `hello-world` placeholder from Phase 2.

### ✅ Definition of done
- [ ] A PR triggers `app-ci.yml` test/build/scan and `infra-ci.yml` plan-with-PR-comment for `dev`
- [ ] Merging to `main` auto-builds, pushes, and deploys real images to `dev`
- [ ] The dev UI is reachable and shows real functionality
- [ ] Suggestion API `/health` passes the CI smoke test

---

## Phase 4 — Data migration and identity (CSV → PostgreSQL, Entra ID)

This is the one phase that requires **application code changes**, not just infra:

1. Design and write forward-only SQL migrations (recommend `golang-migrate`) for `loans`, `compliance_reports`, and an append-only `audit_log` table, matching the fields currently in `data/loans.csv` and `data/compliance_report.json`.
2. Update `pipeline/main.go` to read/write PostgreSQL instead of the CSV/JSON files (connection string built from `POSTGRES_FQDN` + Managed-Identity-based auth token, not a password in an env var — Postgres Flexible Server supports Entra ID authentication for exactly this reason).
3. Run the migration against `dev`'s PostgreSQL first, backfill from the existing `data/loans.csv`, and validate row counts match.
4. Enable Easy Auth on the UI Container App (`az containerapp auth update` or a Terraform `azurerm_container_app` auth config block) pointing at your Entra ID tenant; define the `Reviewer` and `Admin` app roles in the Entra ID app registration and map them to Entra ID security groups.
5. Update `app.py` to read the logged-in user's roles from the `X-MS-CLIENT-PRINCIPAL` header Easy Auth injects, and gate admin-only actions (e.g. policy bundle uploads) behind the `Admin` role.

> This phase is the largest code-change item in the whole rollout — budget real engineering time for it, separate from the "infra plumbing" work in Phases 1-3.

### ✅ Definition of done
- [ ] `loans`, `compliance_reports`, `audit_log` tables exist in dev PostgreSQL with a backfilled row count matching the CSV
- [ ] `pipeline/main.go` reads/writes Postgres, no longer touches `data/loans.csv` or `data/compliance_report.json` in dev
- [ ] Easy Auth is enabled on the dev UI; logging in requires an Entra ID account
- [ ] Reviewer vs. Admin role gating is enforced in `app.py`

---

## Phase 5 — Observability validation

1. Confirm Application Insights is receiving traces: trigger a UI request and a pipeline run, then check the **Application Insights → Transaction search** blade for both.
2. Confirm the example exception-rate alert (`infra/modules/monitoring`) fires: temporarily force an exception (e.g. hit `/suggest` with malformed JSON) and confirm the configured email receiver gets notified.
3. Add at least one additional alert beyond the example: Postgres CPU/storage percentage, and Container Apps replica count hitting its max (a signal you're under-provisioned).
4. Build a basic Azure Workbook (or reuse Application Insights' default dashboard) covering: request latency (UI, Suggestion API), error rate, nightly pipeline pass/fail count and duration.

### ✅ Definition of done
- [ ] Traces visible end-to-end for both a UI request and a pipeline run
- [ ] Exception-rate alert verified to actually fire and notify
- [ ] Postgres and Container Apps capacity alerts added
- [ ] A dashboard exists that a reviewer/on-call engineer could actually use during an incident

---

## Phase 6 — Promote to staging

1. Repeat Phase 1.1's storage-container step is **not** needed again (same shared storage account) — but you do need `terraform init` to succeed for `staging`, which just needs the `staging` GitHub Environment's OIDC federated credential (already created in 1.2) and its own `POSTGRES_ADMIN_PASSWORD` secret (already set in 1.4).
2. Run the *first* `staging` apply locally too (same reasoning as Phase 2 — watch it interactively once):
   ```bash
   cd infra/environments/staging
   terraform init
   terraform plan -var="ui_image=<dev's proven image>:<sha>" -var="api_image=..." -var="pipeline_image=..." -var="postgres_admin_password=<staging password>"
   terraform apply <same vars>
   ```
3. From then on, use [.github/workflows/promote.yml](../.github/workflows/promote.yml) exclusively — trigger it via `workflow_dispatch`, `environment=staging`, `image_tag=<the git SHA that's currently running cleanly in dev>`. This requires 1 reviewer approval (the GitHub Environment gate).
4. Run a load/soak test against staging (tool of your choice — k6, Locust) sized to your expected real traffic, watching the dashboard from Phase 5.
5. Only after staging has run cleanly for a meaningful soak period (recommend at least a few days of real or synthetic traffic) do you move to Phase 7.

### ✅ Definition of done
- [ ] `staging` Terraform state initialized and applied successfully
- [ ] `promote.yml` successfully promotes a dev-proven image tag to staging with 1 reviewer approval
- [ ] Load/soak test completed with no unexpected errors or alert storms
- [ ] Dashboards show healthy latency/error-rate under load

---

## Phase 7 — Production cutover

1. Repeat Phase 6, steps 1-2, for `prod` (first apply run locally, same-shape apply).
2. Trigger `promote.yml` with `environment=prod`, the **same image tag that passed staging's soak test**, and a `change_ticket` reference (the workflow enforces this input is non-empty for prod — see the `guard` job in [promote.yml](../.github/workflows/promote.yml)). Requires 2 reviewer approvals.
3. Watch the traffic-shifted rollout closely: the new revision starts at 0% traffic, the workflow's smoke test hits `/health`, then traffic shifts to 100%. Keep the previous revision's name handy for the next 24-48 hours in case a fast rollback is needed (shift traffic back to it — no rebuild required).
4. Once prod is confirmed stable, decommission the old manual/local demo path (stop treating `data/loans.csv` + local `opa run --server` as anything other than a local-dev convenience).

### ✅ Definition of done
- [ ] `prod` Terraform state initialized and applied successfully
- [ ] `promote.yml` prod run completed with 2 reviewer approvals and a valid change ticket reference
- [ ] Prod smoke test passed; traffic fully shifted to the new revision
- [ ] Team briefed that the CSV/local-OPA path is no longer the source of truth

---

## Ongoing operations (after go-live)

**Making a code change**: PR → `app-ci.yml` test/build/scan → merge → auto-deploy to `dev` → soak → `promote.yml` to `staging` (1 reviewer) → soak → `promote.yml` to `prod` (2 reviewers + change ticket). Never skip a tier.

**Making an infra change**: PR touching `infra/` → `infra-ci.yml` posts a `terraform plan` comment for all 3 environments → review the diff carefully, especially for `staging`/`prod` → merge → `dev` auto-applies → manually run the same `terraform apply` for `staging`/`prod` once you're satisfied (there is currently no automated infra-promotion workflow — this is a deliberate manual gate for infra changes, unlike application deploys).

**Rolling back a bad deploy**: shift Container Apps traffic back to the previous (still-warm) revision — no rebuild, no redeploy. See [docs/production-architecture.md §12.4](production-architecture.md#124-deployment-mechanics-how-a-code-change-actually-reaches-users).

**Rotating the Postgres admin password**: update the GitHub Environment secret, then run `terraform apply` for that environment with the new `-var="postgres_admin_password=..."` — Terraform will update the server in place.

**Rotating/updating the Rego policy**: upload a new bundle version to the `policy-bundle` Blob Storage container and restart/roll the affected Container App(s) — no image rebuild required (see §12.4).

---

## Known gaps carried forward (not blocking this rollout, but on the backlog)

These were identified in the engineering audit and are **explicitly deferred** per team decision — listed here so they aren't forgotten once the rollout is underway:

1. `pipeline/main.go` silently drops loans with an unrecognized currency (missing FX rate) or a failed OPA/network call, with no logging — should fail loudly or log-and-count instead.
2. No automated test coverage (`go test`, `opa test`, `pytest` all currently pass with zero tests) — `app-ci.yml`'s test gate is not yet a meaningful quality bar.
3. `retrieval/api_server.py` trusts client-supplied `Content-Length` with no cap.

Recommend closing at least #1 and #2 before Phase 7 (production cutover) — a silent data-loss bug in a *compliance* pipeline is a real risk once real loan data is on the line, even though it's out of scope for this rollout itself.
