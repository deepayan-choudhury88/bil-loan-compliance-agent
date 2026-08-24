############################################
# Azure Container Registry module
#
# Admin credentials are disabled — every pull is via a Container App's
# Managed Identity + AcrPull role assignment (granted in the
# container_apps module), never a shared admin username/password.
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

variable "sku" {
  type    = string
  default = "Standard"
}

resource "azurerm_container_registry" "this" {
  name                = replace("acrloancompl${var.environment}", "-", "")
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  admin_enabled       = false

  # Microsoft Defender for Containers image scanning is enabled at the
  # subscription level (Defender plan), not per-registry here.
}

output "acr_id" {
  value = azurerm_container_registry.this.id
}

output "acr_login_server" {
  value = azurerm_container_registry.this.login_server
}
