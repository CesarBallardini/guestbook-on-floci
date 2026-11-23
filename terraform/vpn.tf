# The way in for administrators: an OpenVPN server on an instance of its own, in a public
# subnet with an Elastic IP. Ansible deploys through it, and a person with ssh or psql
# connects with a profile from .generated/vpn/.
#
# The server sets itself up at first boot (vpn-user-data.sh.tftpl). Its two secrets, its
# private key and the tls-crypt key, are not in that script: anyone allowed to read an
# instance's attributes can read its user data. They are in Parameter Store, and the
# server's role may read those two parameters and nothing else. Their values, like every key
# here, are also in the Terraform state; the clients' keys are in .generated/vpn/ as well.
#
# The server's files are rendered here once. The script writes them at first boot, and the
# playbook writes the same text again, so a later change still goes through Ansible.

locals {
  # The tunnel's addresses. They must not overlap the VPC. The server is the first one.
  vpn_client_cidr      = "10.8.0.0/24"
  vpn_server_tunnel_ip = cidrhost(local.vpn_client_cidr, 1)
  vpn_server_dir       = "/etc/openvpn/server"

  # The playbook's supervisor_version: the same process manager on both instances.
  vpn_supervisor_version = "4.3.0"

  vpn_server_conf = join("\n", [
    "# Written by Terraform (terraform/vpn.tf); the playbook keeps it so.",
    "port ${var.vpn_port}",
    "proto udp",
    "dev tun",
    "topology subnet",
    "server ${cidrhost(local.vpn_client_cidr, 0)} ${cidrnetmask(local.vpn_client_cidr)}",
    # The VPC, for the people's profiles. The deploy's profile in the emulator takes no route
    # from here (see local.vpn_profiles).
    "push \"route ${cidrhost(var.vpc_cidr, 0)} ${cidrnetmask(var.vpc_cidr)}\"",
    "ca ${local.vpn_server_dir}/ca.crt",
    "cert ${local.vpn_server_dir}/server.crt",
    "key ${local.vpn_server_dir}/server.key",
    # ECDSA keys: ECDHE only, no Diffie-Hellman parameters.
    "dh none",
    # A packet without this key gets no answer at all: to anyone else the port looks closed.
    "tls-crypt ${local.vpn_server_dir}/tls-crypt.key",
    "tls-version-min 1.3",
    "data-ciphers AES-256-GCM:CHACHA20-POLY1305",
    "remote-cert-tls client",
    # Only the clients that have a file there may connect: taking a name out of vpn_clients
    # removes its file, and the server refuses it at its next connection.
    "client-config-dir ${local.vpn_server_dir}/ccd",
    "ccd-exclusive",
    # The package's own user: it can read ccd/, which is root:openvpn and mode 750.
    "user openvpn",
    "group openvpn",
    "persist-key",
    "persist-tun",
    "keepalive 10 60",
    "status /var/log/openvpn-status.log",
    "verb 3",
    "",
  ])

  # supervisord runs OpenVPN in the foreground, as it runs nginx and gunicorn on the app's
  # instance: the instance has no systemd.
  vpn_supervisord_conf = join("\n", [
    "; Written by Terraform (terraform/vpn.tf); the playbook keeps it so.",
    "[supervisord]",
    "user = root",
    "pidfile = /run/supervisord.pid",
    "logfile = /var/log/supervisord.log",
    "",
    "[unix_http_server]",
    "file = /run/supervisor.sock",
    "chmod = 0700",
    "",
    "[rpcinterface:supervisor]",
    "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface",
    "",
    "[supervisorctl]",
    "serverurl = unix:///run/supervisor.sock",
    "",
    "[program:openvpn]",
    "command = openvpn --cd ${local.vpn_server_dir} --config server.conf",
    "autorestart = true",
    "redirect_stderr = true",
    "stdout_logfile = /var/log/openvpn.log",
    "",
  ])

  vpn_user_data = templatefile("${path.module}/vpn-user-data.sh.tftpl", {
    server_dir           = local.vpn_server_dir
    ca_cert              = tls_self_signed_cert.vpn_ca.cert_pem
    server_cert          = tls_locally_signed_cert.vpn_server.cert_pem
    server_conf          = local.vpn_server_conf
    supervisord_conf     = local.vpn_supervisord_conf
    supervisor_version   = local.vpn_supervisor_version
    server_key_parameter = aws_ssm_parameter.vpn_server_key.name
    tls_crypt_parameter  = aws_ssm_parameter.vpn_tls_crypt_key.name
    parameter_store_url  = var.emulator_url_from_instance
    region               = data.aws_region.current.region
    client_cidr          = local.vpn_client_cidr
    deploy_client        = "ansible"
  })
}

# ---- The keys: the VPN's own certificate authority, trusted by nothing else ---------------------

# Renewing a certificate changes the server's files, which replaces the server, or a profile,
# which the person imports again.
resource "tls_private_key" "vpn_ca" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_self_signed_cert" "vpn_ca" {
  private_key_pem       = tls_private_key.vpn_ca.private_key_pem
  is_ca_certificate     = true
  validity_period_hours = 24 * 365 * 3
  early_renewal_hours   = 24 * 30
  allowed_uses          = ["cert_signing", "crl_signing", "digital_signature"]

  subject {
    common_name = "guestbook-vpn-ca"
  }
}

resource "tls_private_key" "vpn_server" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_cert_request" "vpn_server" {
  private_key_pem = tls_private_key.vpn_server.private_key_pem

  # The name the profiles check (verify-x509-name).
  subject {
    common_name = "guestbook-vpn"
  }
}

resource "tls_locally_signed_cert" "vpn_server" {
  cert_request_pem      = tls_cert_request.vpn_server.cert_request_pem
  ca_private_key_pem    = tls_private_key.vpn_ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.vpn_ca.cert_pem
  validity_period_hours = 24 * 90
  early_renewal_hours   = 24 * 30
  allowed_uses          = ["digital_signature", "server_auth"]
}

# One per name in vpn_clients. Short-lived: "terraform apply" renews them in their last 30 days.
resource "tls_private_key" "vpn_client" {
  for_each    = toset(var.vpn_clients)
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_cert_request" "vpn_client" {
  for_each        = tls_private_key.vpn_client
  private_key_pem = each.value.private_key_pem

  subject {
    common_name = each.key
  }
}

resource "tls_locally_signed_cert" "vpn_client" {
  for_each              = tls_cert_request.vpn_client
  cert_request_pem      = each.value.cert_request_pem
  ca_private_key_pem    = tls_private_key.vpn_ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.vpn_ca.cert_pem
  validity_period_hours = 24 * 90
  early_renewal_hours   = 24 * 30
  allowed_uses          = ["digital_signature", "client_auth"]
}

# OpenVPN's tls-crypt key: 2048 bits, in OpenVPN's own format.
resource "random_bytes" "vpn_tls_crypt" {
  length = 256
}

locals {
  vpn_tls_crypt_key = join("\n", concat(
    ["-----BEGIN OpenVPN Static key V1-----"],
    regexall(".{32}", random_bytes.vpn_tls_crypt.hex),
    ["-----END OpenVPN Static key V1-----", ""],
  ))
}

# ---- The server's secrets, and the role that may read them ------------------------------------

resource "aws_ssm_parameter" "vpn_server_key" {
  name        = "/guestbook/vpn/server-key"
  description = "The VPN server's private key. Only the VPN server's role may read it."
  type        = "SecureString"
  value       = tls_private_key.vpn_server.private_key_pem
}

resource "aws_ssm_parameter" "vpn_tls_crypt_key" {
  name        = "/guestbook/vpn/tls-crypt-key"
  description = "The VPN's tls-crypt key. Only the VPN server's role may read it; the profiles carry it too."
  type        = "SecureString"
  value       = local.vpn_tls_crypt_key
}

resource "aws_iam_role" "vpn" {
  name = "guestbook-vpn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# The parameters are encrypted with the AWS-managed key, alias/aws/ssm, whose own policy lets
# Parameter Store decrypt them for a caller allowed to read them.
resource "aws_iam_role_policy" "vpn_secrets" {
  name = "guestbook-vpn-secrets"
  role = aws_iam_role.vpn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParameter"
      Resource = [aws_ssm_parameter.vpn_server_key.arn, aws_ssm_parameter.vpn_tls_crypt_key.arn]
    }]
  })
}

resource "aws_iam_instance_profile" "vpn" {
  name = "guestbook-vpn"
  role = aws_iam_role.vpn.name
}

# ---- The server -------------------------------------------------------------------------------

# Its public address is the Elastic IP. It NATs the tunnel into the VPC, so it needs no
# routes of its own there and keeps source_dest_check. A new user_data makes a new server,
# which sets itself up again: "make replace-vpn" is the answer to a broken one.
#
# It starts after the app's instance: Floci sets each new instance up with downloads that have
# time limits, and two at once both timed out (docs/floci.md, section 5).
resource "aws_instance" "vpn" {
  ami           = var.ami_id
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.all["public-a"].id
  # It has a public address, the Elastic IP: once that is attached, the instance reports one,
  # and "false" here would make every plan replace it.
  associate_public_ip_address = true
  key_name                    = aws_key_pair.ansible.key_name
  vpc_security_group_ids      = [aws_security_group.vpn.id]
  iam_instance_profile        = aws_iam_instance_profile.vpn.name
  user_data                   = local.vpn_user_data
  user_data_replace_on_change = true

  depends_on = [aws_instance.app, aws_iam_role_policy.vpn_secrets]

  tags = {
    Name = "guestbook-vpn"
  }
}

# The address outlives the server: a replaced server gets the same one, so the people's
# profiles keep working. The association is its own resource, replaced with the server: the
# emulator refuses to move an Elastic IP the way aws_eip's own "instance" does it.
resource "aws_eip" "vpn" {
  domain = "vpc"
}

resource "aws_eip_association" "vpn" {
  allocation_id = aws_eip.vpn.id
  instance_id   = aws_instance.vpn.id
}

# ---- The profiles -----------------------------------------------------------------------------

locals {
  # The deploy's profile, in the emulator: Ansible's container is on the same Docker network
  # as the VPN server, so it connects to the server's private address. A route pushed for that
  # network would lose to the container's own route to it, so this profile takes no pushed
  # routes and sends the app's address alone through the tunnel (docs/floci.md). On AWS
  # (vpn_deploy_from_docker_network = false) it is a profile like the people's.
  vpn_deploy_profile_lines = [
    "remote ${aws_instance.vpn.private_ip} ${var.vpn_port}",
    "route-nopull",
    "route ${aws_instance.app.private_ip} 255.255.255.255",
  ]

  vpn_public_profile_lines = [
    "remote ${coalesce(var.vpn_public_host, aws_eip_association.vpn.public_ip)} ${var.vpn_port}",
  ]

  vpn_profiles = {
    for name in var.vpn_clients : name => join("\n", concat(
      [
        "# The VPN profile of \"${name}\". Written by Terraform (terraform/vpn.tf).",
        "client",
        "dev tun",
        "proto udp",
      ],
      name == "ansible" && var.vpn_deploy_from_docker_network ? local.vpn_deploy_profile_lines : local.vpn_public_profile_lines,
      [
        "nobind",
        # Try again every 2 seconds at first, then every 10 at most: a new server takes a few
        # minutes to answer, and OpenVPN's own wait would grow to five minutes.
        "connect-retry 2 10",
        "remote-cert-tls server",
        "verify-x509-name guestbook-vpn name",
        "tls-version-min 1.3",
        "data-ciphers AES-256-GCM:CHACHA20-POLY1305",
        "verb 3",
        "<ca>", trimspace(tls_self_signed_cert.vpn_ca.cert_pem), "</ca>",
        "<cert>", trimspace(tls_locally_signed_cert.vpn_client[name].cert_pem), "</cert>",
        "<key>", trimspace(tls_private_key.vpn_client[name].private_key_pem), "</key>",
        "<tls-crypt>", trimspace(local.vpn_tls_crypt_key), "</tls-crypt>",
        "",
      ],
    ))
  }
}

resource "local_sensitive_file" "vpn_profile" {
  for_each        = local.vpn_profiles
  filename        = "${local.generated_dir}/vpn/${each.key}.ovpn"
  content         = each.value
  file_permission = "0600"
}
