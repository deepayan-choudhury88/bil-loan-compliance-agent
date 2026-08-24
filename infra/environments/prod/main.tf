provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

module "platform" {
  source = "../../platform"

  environment = "prod"
  location    = var.location

  ui_image       = var.ui_image
  api_image      = var.api_image
  pipeline_image = var.pipeline_image

  postgres_admin_login                  = var.postgres_admin_login
  postgres_admin_password               = var.postgres_admin_password
  postgres_sku_name                     = var.postgres_sku_name
  postgres_storage_mb                   = var.postgres_storage_mb
  postgres_geo_redundant_backup_enabled = var.postgres_geo_redundant_backup_enabled

  ui_min_replicas  = var.ui_min_replicas
  ui_max_replicas  = var.ui_max_replicas
  api_max_replicas = var.api_max_replicas

  alert_email = var.alert_email
}

output "ui_fqdn" {
  value = module.platform.ui_fqdn
}

output "postgres_fqdn" {
  value = module.platform.postgres_fqdn
}
