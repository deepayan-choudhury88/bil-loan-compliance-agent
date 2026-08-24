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
  default = "B_Standard_B2s" # one tier up from dev — closer to prod-shaped load testing
}

variable "postgres_storage_mb" {
  type    = number
  default = 65536
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
  default = 3
}

variable "alert_email" {
  type    = string
  default = "compliance-oncall@example.com"
}
