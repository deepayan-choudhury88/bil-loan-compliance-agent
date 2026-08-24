variable "location" {
  type    = string
  default = "eastus"
}

# --- Image references: always passed by CI/CD (-var), never hardcoded ---

variable "ui_image" {
  type = string
}

variable "api_image" {
  type = string
}

variable "pipeline_image" {
  type = string
}

variable "postgres_admin_login" {
  type    = string
  default = "pgadmin"
}

# --- Secrets: passed via TF_VAR_postgres_admin_password from a CI/CD
# secret store (GitHub Environment secret), never committed to a
# .tfvars file. ---
variable "postgres_admin_password" {
  type      = string
  sensitive = true
}

variable "postgres_sku_name" {
  type    = string
  default = "B_Standard_B1ms" # smallest Burstable tier — sufficient for dev
}

variable "postgres_storage_mb" {
  type    = number
  default = 32768
}

variable "ui_min_replicas" {
  type    = number
  default = 1
}

variable "ui_max_replicas" {
  type    = number
  default = 2
}

variable "api_max_replicas" {
  type    = number
  default = 2
}

variable "alert_email" {
  type    = string
  default = "compliance-oncall@example.com"
}
