output "lambda_function_name" {
  value = aws_lambda_function.this.function_name
}

output "lambda_security_group_id" {
  value = aws_security_group.lambda_sg.id
}