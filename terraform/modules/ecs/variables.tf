variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_endpoint" {
  type = string
}

variable "db_security_group_id" {
  type = string
}

variable "container_image" {
  type = string
}