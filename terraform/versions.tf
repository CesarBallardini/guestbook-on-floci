terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
    # The VPN's tls-crypt key: random bytes, which the tls provider can't make.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Every AWS call goes to the emulator. The keys are fake and no AWS account is involved.
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    acm   = var.emulator_url
    ec2   = var.emulator_url
    elbv2 = var.emulator_url
    iam   = var.emulator_url
    rds   = var.emulator_url
    s3    = var.emulator_url
    ssm   = var.emulator_url
    sts   = var.emulator_url
  }
}
