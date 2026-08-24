############################################
# Networking module
#
# Creates the VNET, the delegated subnet used by the Azure Container Apps
# Environment, and a separate subnet for private endpoints (PostgreSQL,
# Key Vault, Storage, ACR). Kept intentionally simple: one VNET per
# environment, no peering — environments are fully isolated from each
# other, which is the safest default for dev/staging/prod separation.
############################################

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "environment" {
  type        = string
  description = "dev | staging | prod"
}

variable "vnet_address_space" {
  type    = list(string)
  default = ["10.20.0.0/16"]
}

variable "container_apps_subnet_prefix" {
  type    = list(string)
  default = ["10.20.0.0/23"]
}

variable "private_endpoints_subnet_prefix" {
  type    = list(string)
  default = ["10.20.2.0/24"]
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-loancompliance-${var.environment}"
  address_space       = var.vnet_address_space
  location            = var.location
  resource_group_name = var.resource_group_name
}

# Delegated subnet required by Container Apps Environment VNET integration.
resource "azurerm_subnet" "container_apps" {
  name                 = "snet-container-apps"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = var.container_apps_subnet_prefix

  delegation {
    name = "container-apps-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Private endpoints (PostgreSQL, Key Vault, Storage, ACR) live here — no
# resource in this subnet ever gets a public IP.
resource "azurerm_subnet" "private_endpoints" {
  name                                          = "snet-private-endpoints"
  resource_group_name                           = var.resource_group_name
  virtual_network_name                          = azurerm_virtual_network.this.name
  address_prefixes                              = var.private_endpoints_subnet_prefix
  private_endpoint_network_policies             = "Enabled"
}

resource "azurerm_network_security_group" "private_endpoints" {
  name                = "nsg-private-endpoints-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  # Deny all inbound by default; private endpoints only need to accept
  # traffic from inside the VNET, which the default VNET-inbound rule
  # already allows at a lower priority than this explicit deny-all.
  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "container_apps_subnet_id" {
  value = azurerm_subnet.container_apps.id
}

output "private_endpoints_subnet_id" {
  value = azurerm_subnet.private_endpoints.id
}
