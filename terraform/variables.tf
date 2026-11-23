variable "emulator_url" {
  description = "The emulator's AWS API, as seen from this machine."
  type        = string
  default     = "http://127.0.0.1:4566"
}

variable "ami_id" {
  description = "The instance's AMI. It must be an imageId of floci/image-catalog.yaml, which maps it to a Docker image."
  type        = string
  default     = "ami-al2023-20261120"
}

variable "listener_port" {
  description = "The load balancer's HTTP port. compose.yaml must publish the same port."
  type        = number
  default     = 8080
}

variable "https_listener_port" {
  description = "The load balancer's HTTPS port. compose.yaml must publish the same port."
  type        = number
  default     = 8443
}

variable "database_host_port" {
  description = "The port of this machine that compose.yaml maps to the RDS instance, for psql."
  type        = number
  default     = 7001
}

variable "postgres_version" {
  description = "The major version of PostgreSQL in the RDS instance."
  type        = string
  default     = "16"
}

variable "database_username" {
  description = "The master user of the RDS instance."
  type        = string
  default     = "postgres"
}

variable "database_password" {
  description = "The password of the emulated RDS instance. It protects nothing: the database is local and holds test messages."
  type        = string
  default     = "development-only"
  sensitive   = true
}

variable "emulator_url_from_instance" {
  description = "The emulator's AWS API, as seen from the EC2 instance: the app's S3. On AWS the app needs no such address."
  type        = string
  default     = "http://aws-emulator:4566"
}

variable "load_balancer_cidr" {
  description = "The addresses the load balancer connects to the instance from. nginx believes the visitor's address only when one of these passes it on. The default holds Docker's bridge networks (the emulator) and the default VPC of an AWS account."
  type        = string
  default     = "172.16.0.0/12"

  validation {
    condition     = can(cidrhost(var.load_balancer_cidr, 0))
    error_message = "load_balancer_cidr must be a network in CIDR form, such as 172.16.0.0/12."
  }
}
