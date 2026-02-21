output "db_endpoint" {
  description = "RDS endpoint hostname."
  value       = module.rds.db_endpoint
}

output "db_port" {
  description = "RDS port."
  value       = module.rds.db_port
}

output "db_name" {
  description = "RDS database name."
  value       = module.rds.db_name
}

output "db_username" {
  description = "RDS master username."
  value       = module.rds.db_username
}

output "db_security_group_id" {
  description = "Security group attached to RDS."
  value       = module.rds.db_security_group_id
}
