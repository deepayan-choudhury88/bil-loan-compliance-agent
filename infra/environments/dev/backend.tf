terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  # Remote state: one storage account/container shared across all three
  # environments, but a DIFFERENT state key (file) per environment, so a
  # mistake in one environment's state can never touch another's.
  # Bootstrap this storage account once, out-of-band, before first use
  # (see infra/README.md "Bootstrapping remote state").
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-shared"
    storage_account_name = "sttfstateloancompl"
    container_name       = "tfstate"
    key                  = "dev.terraform.tfstate"
  }
}
