############################################
# Platform composition module
#
# Wires every child module together into one deployable landing zone.
# This is NOT a Terraform root module itself — it's called by each
# environment (environments/dev, staging, prod), each with its own
# backend/state and .tfvars. See infra/README.md.
############################################

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-loancompl-${var.environment}"
  location = var.location
}

module "networking" {
  source = "../modules/networking"

  resource_group_name = azurerm_resource_group.this.name
  location             = var.location
  environment          = var.environment
}

# Private DNS zone for PostgreSQL Flexible Server VNET integration.
resource "azurerm_private_dns_zone" "postgres" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "pdz-link-postgres-${var.environment}"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = module.networking.vnet_id
}

module "keyvault" {
  source = "../modules/keyvault"

  resource_group_name         = azurerm_resource_group.this.name
  location                    = var.location
  environment                 = var.environment
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  private_endpoints_subnet_id = module.networking.private_endpoints_subnet_id
}

module "storage" {
  source = "../modules/storage"

  resource_group_name         = azurerm_resource_group.this.name
  location                    = var.location
  environment                 = var.environment
  private_endpoints_subnet_id = module.networking.private_endpoints_subnet_id
}

module "acr" {
  source = "../modules/acr"

  resource_group_name = azurerm_resource_group.this.name
  location             = var.location
  environment          = var.environment
}

module "postgresql" {
  source = "../modules/postgresql"

  resource_group_name          = azurerm_resource_group.this.name
  location                     = var.location
  environment                  = var.environment
  private_endpoints_subnet_id  = module.networking.private_endpoints_subnet_id
  private_dns_zone_id          = azurerm_private_dns_zone.postgres.id
  admin_login                  = var.postgres_admin_login
  admin_password                = var.postgres_admin_password
  sku_name                      = var.postgres_sku_name
  storage_mb                    = var.postgres_storage_mb
  geo_redundant_backup_enabled  = var.postgres_geo_redundant_backup_enabled

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

module "monitoring" {
  source = "../modules/monitoring"

  resource_group_name = azurerm_resource_group.this.name
  location             = var.location
  environment          = var.environment
  alert_email          = var.alert_email
}

module "container_apps" {
  source = "../modules/container_apps"

  resource_group_name              = azurerm_resource_group.this.name
  location                         = var.location
  environment                      = var.environment
  container_apps_subnet_id         = module.networking.container_apps_subnet_id
  log_analytics_workspace_id       = module.monitoring.log_analytics_workspace_id
  acr_id                            = module.acr.acr_id
  acr_login_server                 = module.acr.acr_login_server
  key_vault_id                      = module.keyvault.key_vault_id
  key_vault_uri                     = module.keyvault.key_vault_uri
  storage_account_name              = module.storage.storage_account_name
  postgres_fqdn                     = module.postgresql.server_fqdn
  app_insights_connection_string    = module.monitoring.app_insights_connection_string

  ui_image        = var.ui_image
  api_image       = var.api_image
  pipeline_image  = var.pipeline_image
  ui_min_replicas = var.ui_min_replicas
  ui_max_replicas = var.ui_max_replicas
  api_max_replicas = var.api_max_replicas
}
