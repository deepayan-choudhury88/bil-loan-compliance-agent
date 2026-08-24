############################################
# Storage module
#
# Blob Storage for the FAISS vector index + the company-reference source
# document. RA-GRS replication gives read access to a secondary region if
# the primary region is unavailable, supporting the DR targets in the
# architecture doc without standing up a second active environment.
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

variable "replication_type" {
  type    = string
  default = "RAGRS"
}

resource "azurerm_storage_account" "this" {
  name                            = replace("st${var.environment}loancompl", "-", "")
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = var.replication_type
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = false
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "faiss_index" {
  name                  = "faiss-index"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "reference_docs" {
  name                  = "reference-docs"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

# Rego policy bundle — loaded by the pipeline/API at container startup so
# policy changes don't require a full image rebuild (see architecture doc
# §15 risk mitigation).
resource "azurerm_storage_container" "policy_bundle" {
  name                  = "policy-bundle"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id

  private_service_connection {
    name                           = "pe-blob-connection"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
}

output "storage_account_id" {
  value = azurerm_storage_account.this.id
}

output "storage_account_name" {
  value = azurerm_storage_account.this.name
}

output "primary_blob_endpoint" {
  value = azurerm_storage_account.this.primary_blob_endpoint
}
