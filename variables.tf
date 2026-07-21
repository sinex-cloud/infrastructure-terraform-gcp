variable "env" {
  type        = string
  description = "Environment name (dev, int)"
}

variable "project" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "Default region for the Google provider"
  default     = "europe-west1"
}