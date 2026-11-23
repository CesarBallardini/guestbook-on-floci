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
  description = "The emulator's AWS API, as seen from the EC2 instances: the app's S3, and the VPN server's Parameter Store. On AWS neither needs such an address; the VPN server leaves an empty one out."
  type        = string
  default     = "http://aws-emulator:4566"
}

variable "load_balancer_cidr" {
  description = "The addresses the load balancer connects to the instance from. nginx believes the visitor's address only when one of these passes it on. The default holds Docker's bridge networks: in the emulator the load balancer connects from Floci's address there. On AWS it is the public subnets, 10.0.0.0/23."
  type        = string
  default     = "172.16.0.0/12"

  validation {
    condition     = can(cidrhost(var.load_balancer_cidr, 0))
    error_message = "load_balancer_cidr must be a network in CIDR form, such as 172.16.0.0/12."
  }
}

variable "vpc_cidr" {
  description = "The guestbook's VPC. Each tier's subnets are /24s of it (network.tf). It must not overlap the VPN's client addresses, 10.8.0.0/24."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 21))
    error_message = "vpc_cidr must be a network in CIDR form, /16 or smaller prefix, such as 10.0.0.0/16."
  }
}

variable "vpn_clients" {
  description = "Who may connect to the VPN: one certificate and one profile, .generated/vpn/<name>.ovpn, each. Taking a name out refuses it at its next connection. \"ansible\" is the deploy's own and must stay."
  type        = list(string)
  default     = ["ansible"]

  validation {
    condition     = contains(var.vpn_clients, "ansible")
    error_message = "vpn_clients must keep \"ansible\": the deploy connects as it."
  }

  validation {
    condition     = alltrue([for name in var.vpn_clients : can(regex("^[a-z][a-z0-9-]*$", name))]) && length(distinct(var.vpn_clients)) == length(var.vpn_clients)
    error_message = "Each name in vpn_clients is lowercase letters, digits and \"-\", starts with a letter, and appears once."
  }
}

variable "vpn_allowed_cidrs" {
  description = "Where the VPN's port takes packets from. Anywhere by default, because administrators move: a packet without the profile's tls-crypt key gets no answer, so the port looks closed to anyone else."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for cidr in var.vpn_allowed_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Each entry of vpn_allowed_cidrs must be a network in CIDR form."
  }
}

variable "vpn_port" {
  description = "The VPN server's UDP port."
  type        = number
  default     = 1194
}

variable "vpn_public_host" {
  description = "The address the people's VPN profiles connect to. By default the VPN server's Elastic IP. In the emulator that is 127.0.0.1 and the port isn't published, so those profiles are for AWS; the deploy's own profile uses the server's private address."
  type        = string
  default     = null
}

variable "vpn_deploy_from_docker_network" {
  description = "Whether the deploy's VPN profile is for the emulator: Ansible's container then connects to the VPN server's private address on the Docker network, and routes only the app's address through the tunnel. On AWS set it to false: the profile is then like the people's."
  type        = bool
  default     = true
}
