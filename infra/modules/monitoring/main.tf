############################################
# Monitoring module
#
# One Log Analytics workspace + workspace-based Application Insights per
# environment, an action group for alert notifications, and a couple of
# starter alert rules. Extend with more `azurerm_monitor_*_alert`
# resources as real usage patterns emerge (see architecture doc §9).
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

variable "alert_email" {
  type = string
}

variable "retention_in_days" {
  type    = number
  default = 30
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "law-loancompl-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days    = var.retention_in_days
}

resource "azurerm_application_insights" "this" {
  name                = "appi-loancompl-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
}

resource "azurerm_monitor_action_group" "this" {
  name                = "ag-loancompl-${var.environment}"
  resource_group_name = var.resource_group_name
  short_name          = "loancompl"

  email_receiver {
    name          = "oncall"
    email_address = var.alert_email
  }
}

# Example alert: fires if the exception rate spikes across any component
# reporting into this Application Insights instance. Threshold is a
# starting point — tune after observing real baseline traffic.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "exception_rate" {
  name                = "alert-exception-rate-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  severity            = 2
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [azurerm_application_insights.this.id]

  criteria {
    query                   = <<-QUERY
      exceptions
      | summarize count()
    QUERY
    time_aggregation_method = "Count"
    threshold               = 20
    operator                = "GreaterThan"
  }

  action {
    action_groups = [azurerm_monitor_action_group.this.id]
  }
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}

output "app_insights_instrumentation_key" {
  value     = azurerm_application_insights.this.instrumentation_key
  sensitive = true
}
