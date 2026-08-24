variable "location" {
  type    = string
  default = "eastus"
}

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

variable "postgres_admin_password" {
  type      = string
  sensitive = true
}

variable "postgres_sku_name" {
  type    = string
  default = "GP_Standard_D2s_v3" # General Purpose — headroom for real portfolio sizes
}

variable "postgres_storage_mb" {
  type    = number
  default = 131072
}

variable "postgres_geo_redundant_backup_enabled" {
  type    = bool
  default = true # meets the RPO target in the architecture doc §8
}

variable "ui_min_replicas" {
  type    = number
  default = 2 # no cold-start risk for the production reviewer UI
}

variable "ui_max_replicas" {
  type    = number
  default = 5
}

variable "api_max_replicas" {
  type    = number
  default = 10
}

variable "alert_email" {
  type    = string
  default = "compliance-oncall@example.com"
}
