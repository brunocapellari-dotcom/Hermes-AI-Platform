terraform {
  required_version = ">= 1.10"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.8.1"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
