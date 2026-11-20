# The guestbook's infrastructure, in the emulator: one EC2 instance, one PostgreSQL RDS instance
# and a load balancer in front of the instance. Ansible installs the app afterwards.
#
#   docker compose up -d --wait      # the emulator, from the folder above
#   terraform init
#   terraform apply

locals {
  # What Terraform writes for Ansible: the SSH private key and the inventory. Ignored by Git.
  generated_dir = "${path.module}/../.generated"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---- The instance -----------------------------------------------------------------------------

resource "tls_private_key" "ansible" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "ansible" {
  key_name   = "guestbook-ansible"
  public_key = tls_private_key.ansible.public_key_openssh
}

resource "local_sensitive_file" "ansible_private_key" {
  filename        = "${local.generated_dir}/id_ed25519"
  content         = tls_private_key.ansible.private_key_openssh
  file_permission = "0600"
}

resource "aws_security_group" "app" {
  name        = "guestbook-app"
  description = "SSH for Ansible and HTTP for the load balancer, from inside the VPC"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    description = "Out to anywhere: the instance downloads its packages"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami                    = var.ami_id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.ansible.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  tags = {
    Name = "guestbook"
  }
}

# ---- The pictures -----------------------------------------------------------------------------

data "aws_region" "current" {}

resource "aws_s3_bucket" "pictures" {
  bucket        = "guestbook-pictures"
  force_destroy = true
}

# The app holds no AWS keys. The instance has a role that may read and write the pictures, and
# the app gets the role's temporary credentials from the instance metadata service.
resource "aws_iam_role" "app" {
  name = "guestbook-app"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "pictures" {
  name = "guestbook-pictures"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.pictures.arn}/*"
    }]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "guestbook-app"
  role = aws_iam_role.app.name
}

# ---- The database -----------------------------------------------------------------------------

# No "port": the emulator serves each RDS instance on a port of its own choice, from 7001.
resource "aws_db_instance" "guestbook" {
  identifier          = "guestbook"
  engine              = "postgres"
  engine_version      = var.postgres_version
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  db_name             = "guestbook"
  username            = var.database_username
  password            = var.database_password
  skip_final_snapshot = true
}

# ---- The load balancer ------------------------------------------------------------------------

resource "aws_lb" "guestbook" {
  name               = "guestbook"
  load_balancer_type = "application"
  subnets            = slice(sort(data.aws_subnets.default.ids), 0, 2)
}

resource "aws_lb_target_group" "app" {
  name        = "guestbook-app"
  port        = 80
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    path              = "/health"
    matcher           = "200"
    interval          = 10
    healthy_threshold = 2
  }
}

resource "aws_lb_target_group_attachment" "app" {
  target_group_arn = aws_lb_target_group.app.arn
  target_id        = aws_instance.app.id
  port             = 80
}

# The emulator's Certificate Manager issues a certificate of its own, at no cost as on AWS. No
# browser trusts its issuer, so the browser warns once.
resource "aws_acm_certificate" "guestbook" {
  domain_name       = "localhost"
  validation_method = "DNS"
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.guestbook.arn
  port              = var.https_listener_port
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.guestbook.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# Plain HTTP serves nothing: it sends the browser to the same address over HTTPS. The host, the
# path and the query are kept. Everything behind this load balancer is a page for a browser,
# so nothing is redirected that a program would rather see refused.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.guestbook.arn
  port              = var.listener_port
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol = "HTTPS"
      port     = tostring(var.https_listener_port)
      # Floci 2.5.0 keeps the leading "/" in #{path}; AWS removes it. With the usual "/#{path}"
      # the emulator would send the browser to "//". On AWS this must be "/#{path}", the
      # default: AWS refuses a path that does not start with "/".
      path        = "#{path}"
      status_code = "HTTP_301"
    }
  }
}

# ---- For Ansible ------------------------------------------------------------------------------

# The inventory: where the instance is, and what the app needs to know about the database.
# The key's path is where the Ansible container puts its copy of the key.
resource "local_sensitive_file" "ansible_inventory" {
  filename        = "${local.generated_dir}/inventory.yml"
  file_permission = "0600"
  content = yamlencode({
    all = {
      hosts = {
        guestbook = {
          ansible_host                 = aws_instance.app.private_ip
          ansible_user                 = "root"
          ansible_ssh_private_key_file = "/tmp/id_ed25519"
          database_url                 = "postgresql://${var.database_username}:${urlencode(var.database_password)}@${aws_db_instance.guestbook.address}:${aws_db_instance.guestbook.port}/${aws_db_instance.guestbook.db_name}"
          picture_bucket               = aws_s3_bucket.pictures.bucket
          s3_endpoint_url              = var.emulator_url_from_instance
          aws_region                   = data.aws_region.current.region
          load_balancer_cidr           = var.load_balancer_cidr
        }
      }
    }
  })
}
