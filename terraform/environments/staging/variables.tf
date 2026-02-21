variable "aws_region" {
  type    = string
  default = "ca-central-1"
}

variable "db_username" {
  type    = string
  default = "contribnow_admin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

