module "networking" {
  source = "../../modules/networking"

  vpc_cidr            = "10.0.0.0/16"
  public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnet_cidrs = ["10.0.3.0/24", "10.0.4.0/24"]
  environment         = "dev"
}

module "s3" {
  source        = "../../modules/s3"
  environment   = "dev"
  bucket_prefix = "contribnow-datalake"
}

module "rds" {
  source = "../../modules/rds"

  environment = "dev"
  db_name     = "contribnow_dev"
  db_username = var.db_username
  db_password = var.db_password

  vpc_id                   = module.networking.vpc_id
  private_subnet_ids       = module.networking.private_subnet_ids
  allowed_security_group_ids = [
  #   module.lambda.lambda_security_group_id,
  #   module.ecs.ecs_security_group_id,
  ]
}

# Temporarily commented out due to: cost concerns
# module "ecs" {
#   source = "../../modules/ecs"

#   environment        = "dev"
#   vpc_id             = module.networking.vpc_id
#   public_subnet_ids  = module.networking.public_subnet_ids
#   private_subnet_ids = module.networking.private_subnet_ids

#   db_endpoint        = module.rds_postgres.db_endpoint
#   db_security_group_id = module.rds_postgres.db_security_group_id

#   container_image = "nginx:latest"
# }

# Temporarily commented out due to: no lambda.zip
# module "lambda" {
#   source = "../../modules/lambda"

#   environment          = "dev"
#   lambda_zip_path      = "../../lambda/lambda.zip"
#   vpc_id               = module.networking.vpc_id
#   private_subnet_ids   = module.networking.private_subnet_ids
#   rds_security_group_id = module.rds_postgres.db_security_group_id
#   db_endpoint          = module.rds_postgres.db_endpoint
#   db_name              = "contribnow_dev"
#   db_username          = "contribnow_admin"
#   db_password          = var.db_password
#   s3_bucket_name       = module.s3_data_lake.bucket_name
# }
