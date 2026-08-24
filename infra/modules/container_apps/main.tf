############################################
# Container Apps module
#
# One Container Apps Environment hosting all three workloads (see
# architecture doc §4/§10 for why one shared environment instead of
# AKS/App Service/Functions):
#   - "ui"            : Streamlit reviewer UI, public ingress, min 1 replica
#   - "suggestion-api" : RAG suggestion API, internal ingress, scale-to-zero
#   - "pipeline"       : Container Apps Job, scheduled + manually triggerable
#
# Each has a system-assigned Managed Identity with least-privilege role
# assignments — no secrets are ever baked into the image or env vars.
############################################

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "environment" {
  type = string
}

variable "container_apps_subnet_id" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "acr_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "key_vault_id" {
  type = string
}

variable "key_vault_uri" {
  type = string
}

variable "storage_account_name" {
  type = string
}

variable "postgres_fqdn" {
  type = string
}

variable "app_insights_connection_string" {
  type      = string
  sensitive = true
}

variable "ui_image" {
  description = "Full ACR image reference, e.g. <acr>.azurecr.io/ui:<git-sha>"
  type        = string
}

variable "api_image" {
  type = string
}

variable "pipeline_image" {
  type = string
}

variable "ui_min_replicas" {
  type    = number
  default = 1
}

variable "ui_max_replicas" {
  type    = number
  default = 3
}

variable "api_max_replicas" {
  type    = number
  default = 5
}

variable "pipeline_schedule_cron" {
  description = "Cron expression for the scheduled compliance run"
  type        = string
  default     = "0 2 * * *" # nightly at 02:00 UTC
}

data "azurerm_client_config" "current" {}

resource "azurerm_container_app_environment" "this" {
  name                       = "cae-loancompl-${var.environment}"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  log_analytics_workspace_id = var.log_analytics_workspace_id
  infrastructure_subnet_id   = var.container_apps_subnet_id
}

# ---------------------------------------------------------------------
# Reviewer UI (Streamlit) — public ingress via the environment; the
# actual public entry point is Azure Front Door + WAF in front of this
# (see architecture doc §5.3), not a direct public IP on the app itself.
# ---------------------------------------------------------------------
resource "azurerm_container_app" "ui" {
  name                         = "ca-ui-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Multiple" # required for traffic-split rollout/rollback

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = var.acr_login_server
    identity = "System"
  }

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.ui_min_replicas
    max_replicas = var.ui_max_replicas

    container {
      name   = "ui"
      image  = var.ui_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "SUGGESTION_API_URL"
        value = "https://${azurerm_container_app.suggestion_api.ingress[0].fqdn}/suggest"
      }
      env {
        name  = "AZURE_KEY_VAULT_URI"
        value = var.key_vault_uri
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "app-insights-connection-string"
      }
    }
  }

  secret {
    name  = "app-insights-connection-string"
    value = var.app_insights_connection_string
  }

  # Terraform owns the SHAPE of this app (replicas, ingress, secrets); the
  # app-ci.yml deploy job owns WHICH image tag is currently running (via
  # `az containerapp update --image ...`), rolled out as a new revision
  # with a traffic-shifted rollout (see architecture doc §12.4). Without
  # this, the next `terraform apply` would silently roll the app back to
  # whatever image tag is in `var.ui_image` at plan time.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# ---------------------------------------------------------------------
# Suggestion API — internal ingress only, scale-to-zero when idle
# (see architecture doc §10 cost trade-off table).
# ---------------------------------------------------------------------
resource "azurerm_container_app" "suggestion_api" {
  name                         = "ca-api-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Multiple"

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = var.acr_login_server
    identity = "System"
  }

  ingress {
    external_enabled = false # internal-only: reachable within the CAE VNET only
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0 # scale-to-zero: only pay for compute while in use
    max_replicas = var.api_max_replicas

    container {
      name   = "suggestion-api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_KEY_VAULT_URI"
        value = var.key_vault_uri
      }
      env {
        name  = "RAG_STORAGE_ACCOUNT"
        value = var.storage_account_name
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "app-insights-connection-string"
      }
    }
  }

  secret {
    name  = "app-insights-connection-string"
    value = var.app_insights_connection_string
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# ---------------------------------------------------------------------
# Compliance pipeline — Container Apps Job: scheduled nightly, and also
# manually triggerable ("Re-run now" from the UI calls the Azure REST API
# / az CLI to start a job execution on demand).
# ---------------------------------------------------------------------
resource "azurerm_container_app_job" "pipeline" {
  name                         = "caj-pipeline-${var.environment}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = var.acr_login_server
    identity = "System"
  }

  replica_timeout_in_seconds = 1800
  replica_retry_limit        = 1

  schedule_trigger_config {
    cron_expression          = var.pipeline_schedule_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "pipeline"
      image  = var.pipeline_image
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "POSTGRES_FQDN"
        value = var.postgres_fqdn
      }
      env {
        name  = "AZURE_KEY_VAULT_URI"
        value = var.key_vault_uri
      }
      env {
        name  = "SUGGESTION_API_URL"
        value = "https://${azurerm_container_app.suggestion_api.ingress[0].fqdn}/suggest"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "app-insights-connection-string"
      }
    }
  }

  secret {
    name  = "app-insights-connection-string"
    value = var.app_insights_connection_string
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# ---------------------------------------------------------------------
# Least-privilege role assignments for each Managed Identity.
# ---------------------------------------------------------------------
resource "azurerm_role_assignment" "ui_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.ui.identity[0].principal_id
}

resource "azurerm_role_assignment" "api_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.suggestion_api.identity[0].principal_id
}

resource "azurerm_role_assignment" "pipeline_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app_job.pipeline.identity[0].principal_id
}

resource "azurerm_role_assignment" "api_keyvault_secrets_user" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.suggestion_api.identity[0].principal_id
}

resource "azurerm_role_assignment" "pipeline_keyvault_secrets_user" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app_job.pipeline.identity[0].principal_id
}

resource "azurerm_role_assignment" "ui_keyvault_secrets_user" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.ui.identity[0].principal_id
}

output "container_app_environment_id" {
  value = azurerm_container_app_environment.this.id
}

output "ui_fqdn" {
  value = azurerm_container_app.ui.ingress[0].fqdn
}

output "suggestion_api_fqdn" {
  value = azurerm_container_app.suggestion_api.ingress[0].fqdn
}

output "pipeline_job_name" {
  value = azurerm_container_app_job.pipeline.name
}
