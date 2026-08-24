############################################
# PostgreSQL module
#
# Azure Database for PostgreSQL Flexible Server, Burstable tier by
# default (see architecture doc §10 for the cost/capability trade-off
# vs. Cosmos DB). VNET-injected (not just private-endpoint) so it's
# never reachable from outside the private endpoints subnet.
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

variable "private_endpoints_subnet_id" {
  type = string
}

variable "private_dns_zone_id" {
  type = string
}

variable "admin_login" {
  type    = string
  default = "pgadmin"
}

variable "admin_password" {
  type      = string
  sensitive = true
}

variable "sku_name" {
  type    = string
  default = "B_Standard_B1ms"
}

variable "storage_mb" {
  type    = number
  default = 32768
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "geo_redundant_backup_enabled" {
  type    = bool
  default = false
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "psql-loancompl-${var.environment}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "15"
  delegated_subnet_id           = var.private_endpoints_subnet_id
  private_dns_zone_id           = var.private_dns_zone_id
  administrator_login           = var.admin_login
  administrator_password        = var.admin_password
  sku_name                      = var.sku_name
  storage_mb                    = var.storage_mb
  backup_retention_days         = var.backup_retention_days
  geo_redundant_backup_enabled  = var.geo_redundant_backup_enabled
  public_network_access_enabled = false
}

resource "azurerm_postgresql_flexible_server_database" "loan_compliance" {
  name      = "loan_compliance"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

output "server_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "server_id" {
  value = azurerm_postgresql_flexible_server.this.id
}

output "database_name" {
  value = azurerm_postgresql_flexible_server_database.loan_compliance.name
}
