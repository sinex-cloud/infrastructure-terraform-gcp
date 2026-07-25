output "dataset_ids" {
  description = "BigQuery dataset IDs managed in this environment, keyed by dataset name"
  value       = module.data_platform.dataset_ids
}

output "bucket_names" {
  description = "Cloud Storage bucket names managed in this environment, keyed by bucket key"
  value       = module.data_platform.bucket_names
}
