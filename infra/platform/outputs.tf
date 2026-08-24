output "ui_fqdn" {
  description = "Public FQDN of the reviewer UI (fronted by Azure Front Door + WAF in production)"
  value       = module.container_apps.ui_fqdn
}

output "suggestion_api_fqdn" {
  description = "Internal-only FQDN of the suggestion API"
  value       = module.container_apps.suggestion_api_fqdn
}

output "pipeline_job_name" {
  value = module.container_apps.pipeline_job_name
}

output "acr_login_server" {
  value = module.acr.acr_login_server
}

output "postgres_fqdn" {
  value = module.postgresql.server_fqdn
}

output "key_vault_uri" {
  value = module.keyvault.key_vault_uri
}

output "resource_group_name" {
  value = azurerm_resource_group.this.name
}
