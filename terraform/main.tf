# The guestbook's infrastructure, in the emulator: one EC2 instance, one PostgreSQL RDS instance
# and a load balancer in front of the instance, in a network of their own (network.tf), and a
# VPN server for the administrators (vpn.tf). Ansible installs the app afterwards.
#
#   docker compose up -d --wait      # the emulator, from the folder above
#   terraform init
#   terraform apply

locals {
  # What Terraform writes for Ansible: the SSH private key, the inventory and the VPN's
  # profiles. Ignored by Git.
  generated_dir = "${path.module}/../.generated"
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

# In an app subnet, with no public address: the load balancer and the VPN server reach it.
resource "aws_instance" "app" {
  ami                         = var.ami_id
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.all["app-a"].id
  associate_public_ip_address = false
  key_name                    = aws_key_pair.ansible.key_name
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name

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
# the app gets the role's temporary credentials from the instance metadata service. The role
# may do it only through the VPC's S3 endpoint, so its credentials are of no use elsewhere.
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
      Condition = {
        StringEquals = { "aws:SourceVpce" = aws_vpc_endpoint.s3.id }
      }
    }]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "guestbook-app"
  role = aws_iam_role.app.name
}

# ---- The database -----------------------------------------------------------------------------

resource "aws_db_subnet_group" "guestbook" {
  name       = "guestbook"
  subnet_ids = [aws_subnet.all["data-a"].id, aws_subnet.all["data-b"].id]
}

# No "port": the emulator serves each RDS instance on a port of its own choice, from 7001.
# In the data subnets, with no public address.
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

  db_subnet_group_name   = aws_db_subnet_group.guestbook.name
  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.db.id]
}

# ---- The load balancer ------------------------------------------------------------------------

# The one thing on the internet for visitors.
resource "aws_lb" "guestbook" {
  name               = "guestbook"
  load_balancer_type = "application"
  internal           = false
  subnets            = [aws_subnet.all["public-a"].id, aws_subnet.all["public-b"].id]
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "app" {
  name        = "guestbook-app"
  port        = 80
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = aws_vpc.guestbook.id

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

# The inventory: where the instance and the VPN server are, and what the app needs to know about
# the database. Ansible reaches both through the VPN: the instance at its private address, the
# VPN server at its address in the tunnel. The key's path is where the Ansible container puts
# its copy of the key.
resource "local_sensitive_file" "ansible_inventory" {
  filename        = "${local.generated_dir}/inventory.yml"
  file_permission = "0600"
  content = yamlencode({
    all = {
      vars = {
        ansible_user                 = "root"
        ansible_ssh_private_key_file = "/tmp/id_ed25519"
      }
      children = {
        vpn = {
          hosts = {
            guestbook-vpn = {
              ansible_host         = local.vpn_server_tunnel_ip
              vpn_server_conf      = local.vpn_server_conf
              vpn_supervisord_conf = local.vpn_supervisord_conf
              vpn_clients          = var.vpn_clients
            }
          }
        }
        app = {
          hosts = {
            guestbook = {
              ansible_host       = aws_instance.app.private_ip
              database_url       = "postgresql://${var.database_username}:${urlencode(var.database_password)}@${aws_db_instance.guestbook.address}:${aws_db_instance.guestbook.port}/${aws_db_instance.guestbook.db_name}"
              picture_bucket     = aws_s3_bucket.pictures.bucket
              s3_endpoint_url    = var.emulator_url_from_instance
              aws_region         = data.aws_region.current.region
              load_balancer_cidr = var.load_balancer_cidr
            }
          }
        }
      }
    }
  })
}
