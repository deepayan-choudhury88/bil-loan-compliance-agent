variable "environment" {
  description = "dev | staging | prod"
  type        = string
}

variable "location" {
  type    = string
  default = "eastus"
}

# --- Container images (populated by CI/CD, never hardcoded) ---

variable "ui_image" {
  type = string
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

# --- PostgreSQL sizing (environment-specific via tfvars) ---

variable "postgres_admin_login" {
  type    = string
  default = "pgadmin"
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
}

variable "postgres_sku_name" {
  type    = string
  default = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  type    = number
  default = 32768
}

variable "postgres_geo_redundant_backup_enabled" {
  type    = bool
  default = false
}

# --- Alerting ---

variable "alert_email" {
  type = string
}
