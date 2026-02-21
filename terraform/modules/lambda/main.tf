# IAM role for lambda
resource "aws_iam_role" "lambda_role" {
  name = "contribnow-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Attach LambdaBasicExecution policy
resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# S3 access policy
resource "aws_iam_role_policy" "s3_policy" {
  name = "contribnow-${var.environment}-lambda-s3"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ]
      Resource = [
        "arn:aws:s3:::${var.s3_bucket_name}",
        "arn:aws:s3:::${var.s3_bucket_name}/*"
      ]
    }]
  })
}

# Security group for lambda
resource "aws_security_group" "lambda_sg" {
  name   = "contribnow-${var.environment}-lambda-sg"
  vpc_id = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Lambda function
resource "aws_lambda_function" "this" {
  function_name = "contribnow-${var.environment}-pipeline"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  filename      = var.lambda_zip_path
  timeout       = 60
  memory_size   = 512

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      DB_HOST     = var.db_endpoint
      DB_NAME     = var.db_name
      DB_USER     = var.db_username
      DB_PASS     = var.db_password
      S3_BUCKET   = var.s3_bucket_name
      ENVIRONMENT = var.environment
    }
  }
}