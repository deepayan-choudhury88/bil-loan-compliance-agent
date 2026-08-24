# Non-secret defaults for the dev environment.
# Secrets (postgres_admin_password) and image tags (ui_image, api_image,
# pipeline_image) are injected by CI/CD via -var / TF_VAR_* — never
# committed here.

location          = "eastus"
ui_min_replicas   = 1
ui_max_replicas   = 2
api_max_replicas  = 2
postgres_sku_name = "B_Standard_B1ms"
alert_email       = "compliance-oncall@example.com"
