# Security group for RDS
resource "aws_security_group" "rds" {
  name        = "contribnow-${var.environment}-rds-sg"
  description = "Allow DB access from application layer"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# DB subnet group
resource "aws_db_subnet_group" "this" {
  name       = "contribnow-${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "contribnow-${var.environment}-db-subnet-group"
  }
}

# Postgres instance
resource "aws_db_instance" "this" {
  identifier             = "contribnow-${var.environment}-db"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 20
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_period
  multi_az                = var.multi_az
  deletion_protection     = var.deletion_protection
  skip_final_snapshot     = var.skip_final_snapshot

  tags = {
    Name        = "contribnow-${var.environment}-postgres"
    Environment = var.environment
  }
}

