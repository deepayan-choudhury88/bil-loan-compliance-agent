# Infrastructure as Code — Terraform

This directory implements the target architecture described in
[docs/production-architecture.md](../docs/production-architecture.md).
It is a **starter skeleton**: syntactically complete and representative
of the real resource shapes, but it has not been applied against a real
subscription. Review SKUs, naming, and region choices against your
actual Azure subscription/quota before running `terraform apply`.

## Layout

```
infra/
├── modules/            # Reusable building blocks, one per Azure capability
│   ├── networking/       # VNET, Container Apps subnet, private endpoints subnet
│   ├── keyvault/         # Key Vault + private endpoint, RBAC-authorized
│   ├── storage/          # Blob Storage: FAISS index, reference docs, policy bundle
│   ├── acr/              # Azure Container Registry (no admin credentials)
│   ├── postgresql/       # PostgreSQL Flexible Server (VNET-injected)
│   ├── monitoring/       # Log Analytics + App Insights + alerts
│   └── container_apps/   # Container Apps Environment + ui/api/pipeline workloads
├── platform/           # Composes all modules into one landing zone
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── environments/       # One folder per environment; each is a true Terraform root
    ├── dev/
    ├── staging/
    └── prod/
```

`platform/` is **not** a Terraform root module on its own — it has no
`backend` or `provider` configuration. Each environment under
`environments/` is the actual root: it declares the backend, the
provider, and calls `../../platform` with environment-specific sizing.

## Why one remote state file per environment (not shared workspaces)

Each environment's `backend.tf` points at the same storage account but a
**different state key** (`dev.terraform.tfstate`, `staging...`,
`prod...`). This means a mistake while working in `dev` can never
corrupt or affect `staging`/`prod` state — there's no shared workspace
context to accidentally operate in the wrong one.

## Bootstrapping remote state (one-time, out-of-band)

Terraform can't create the storage account that holds its own state, so
this is done once, manually or via a separate bootstrap script, **before**
any environment's `terraform init` will succeed:

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
# Enable blob versioning so any bad apply's prior state is recoverable:
az storage account blob-service-properties update \
  --account-name sttfstateloancompl \
  --enable-versioning true
```

## Authentication (CI/CD → Azure)

No client secret is ever stored in GitHub. GitHub Actions authenticates
via **OIDC federated credentials** to an Azure AD App Registration:

```bash
az ad app create --display-name "gh-actions-loancompl"
az ad app federated-credential create \
  --id <app-object-id> \
  --parameters '{
    "name": "gh-actions-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<org>/<repo>:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

Grant the resulting Service Principal `Contributor` on each
environment's resource group only (not subscription-wide), plus
`Storage Blob Data Contributor` on the `sttfstateloancompl` storage
account for state read/write.

## Local usage (per environment)

```bash
cd infra/environments/dev
terraform init
terraform plan \
  -var="ui_image=<acr>.azurecr.io/ui:<tag>" \
  -var="api_image=<acr>.azurecr.io/api:<tag>" \
  -var="pipeline_image=<acr>.azurecr.io/pipeline:<tag>" \
  -var="postgres_admin_password=<from a secret manager, never a file>"
terraform apply <same -var flags as plan>
```

In CI/CD, the same commands run with `-var` values sourced from GitHub
Environment secrets/variables — see
[.github/workflows/infra-ci.yml](../.github/workflows/infra-ci.yml) and
[.github/workflows/promote.yml](../.github/workflows/promote.yml).

## What's intentionally left as a follow-up

- Azure Front Door + WAF in front of the UI (module not yet written —
  add `modules/front_door/` when Phase 3 of the rollout plan begins).
- Container image build/push is handled entirely by
  [.github/workflows/app-ci.yml](../.github/workflows/app-ci.yml), not by
  Terraform — Terraform only ever references an image tag that already
  exists in ACR.
- Database schema/migrations are handled by a dedicated migration tool
  (e.g. `golang-migrate`) run as a pipeline step, not by Terraform.
