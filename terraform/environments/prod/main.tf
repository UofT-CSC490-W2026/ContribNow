locals {
  environment = "prod"

  rds_config = {
    db_instance_class       = "db.t3.micro"
    multi_az                = false
    deletion_protection     = false
    backup_retention_period = 1
    skip_final_snapshot     = true
  }
}

module "networking" {
  source = "../../modules/networking"

  vpc_cidr             = "10.2.0.0/16"
  public_subnet_cidrs  = ["10.2.1.0/24", "10.2.2.0/24"]
  private_subnet_cidrs = ["10.2.3.0/24", "10.2.4.0/24"]
  environment          = local.environment
}

module "s3" {
  source        = "../../modules/s3"
  environment   = local.environment
  bucket_prefix = "contribnow-datalake"
}

module "rds" {
  source = "../../modules/rds"

  environment = local.environment

  db_name     = "contribnow_prod"
  db_username = var.db_username
  db_password = var.db_password

  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  allowed_security_group_ids = [
    #   module.lambda.lambda_security_group_id,
    #   module.ecs.ecs_security_group_id,
  ]

  db_instance_class       = local.rds_config.db_instance_class
  multi_az                = local.rds_config.multi_az
  deletion_protection     = local.rds_config.deletion_protection
  backup_retention_period = local.rds_config.backup_retention_period
  skip_final_snapshot     = local.rds_config.skip_final_snapshot
}

# module "ecs" {
#   source = "../../modules/ecs"
# 
#   environment        = "prod"
#   vpc_id             = module.networking.vpc_id
#   public_subnet_ids  = module.networking.public_subnet_ids
#   private_subnet_ids = module.networking.private_subnet_ids
# 
#   db_endpoint        = module.rds_postgres.db_endpoint
#   db_security_group_id = module.rds_postgres.db_security_group_id
# 
#   container_image = "nginx:latest"
# }
# 
# module "lambda" {
#   source = "../../modules/lambda"
# 
#   environment          = "prod"
#   lambda_zip_path      = "../../lambda/lambda.zip"
#   vpc_id               = module.networking.vpc_id
#   private_subnet_ids   = module.networking.private_subnet_ids
#   rds_security_group_id = module.rds_postgres.db_security_group_id
#   db_endpoint          = module.rds_postgres.db_endpoint
#   db_name              = "contribnow_prod"
#   db_username          = "contribnow_admin"
#   db_password          = var.db_password
#   s3_bucket_name       = module.s3_data_lake.bucket_name
# }

