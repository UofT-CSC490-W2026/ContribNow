output "ec2_instance_id" {
  value = module.ec2.instance_id
}

output "ec2_public_ip" {
  value = module.ec2.public_ip
}

output "ec2_security_group_id" {
  value = module.ec2.security_group_id
}

output "db_endpoint" {
  description = "RDS endpoint hostname."
  value       = module.rds.db_endpoint
}

output "db_port" {
  description = "RDS port."
  value       = module.rds.db_port
}

output "db_security_group_id" {
  description = "Security group attached to RDS."
  value       = module.rds.db_security_group_id
}

output "db_name" {
  description = "RDS database name."
  value       = module.rds.db_name
}

output "db_username" {
  description = "RDS master username."
  value       = module.rds.db_username
}
