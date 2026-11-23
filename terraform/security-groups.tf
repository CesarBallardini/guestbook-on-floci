# One security group per role. Every rule is an entry of the two maps below, named for what it
# lets through, and names its peer group rather than an address wherever it can. Only the
# load balancer and the VPN server take anything from the internet.
#
# The emulator records the rules and enforces none (docs/floci.md, section 5);
# tests/network.tftest.hcl checks them.

resource "aws_security_group" "alb" {
  name        = "guestbook-alb"
  description = "The load balancer: HTTPS and HTTP from the internet, HTTP to the app"
  vpc_id      = aws_vpc.guestbook.id
}

resource "aws_security_group" "app" {
  name        = "guestbook-app"
  description = "The instance: HTTP from the load balancer, SSH from the VPN server"
  vpc_id      = aws_vpc.guestbook.id
}

resource "aws_security_group" "db" {
  name        = "guestbook-db"
  description = "RDS: PostgreSQL from the instance and from the VPN server"
  vpc_id      = aws_vpc.guestbook.id
}

# No SSH in: Ansible reaches the VPN server at its tunnel address, through its own tunnel,
# which no security group sees.
resource "aws_security_group" "vpn" {
  name        = "guestbook-vpn"
  description = "The VPN server: OpenVPN from the administrators"
  vpc_id      = aws_vpc.guestbook.id
}

locals {
  security_group_ids = {
    alb = aws_security_group.alb.id
    app = aws_security_group.app.id
    db  = aws_security_group.db.id
    vpn = aws_security_group.vpn.id
  }

  # Each rule: its group, the protocol and port, and one peer: a group, an address range or a
  # prefix list.
  rule_peers = { peer = null, cidr = null, prefix_list = null }

  ingress_rules = { for name, rule in merge(
    {
      alb_https_from_internet = { group = "alb", protocol = "tcp", port = var.https_listener_port, cidr = "0.0.0.0/0" }
      alb_http_from_internet  = { group = "alb", protocol = "tcp", port = var.listener_port, cidr = "0.0.0.0/0" }
      app_http_from_alb       = { group = "app", protocol = "tcp", port = 80, peer = "alb" }
      app_ssh_from_vpn        = { group = "app", protocol = "tcp", port = 22, peer = "vpn" }
      db_postgres_from_app    = { group = "db", protocol = "tcp", port = 5432, peer = "app" }
      db_postgres_from_vpn    = { group = "db", protocol = "tcp", port = 5432, peer = "vpn" }
    },
    {
      for cidr in var.vpn_allowed_cidrs :
      "vpn_openvpn_from_${cidr}" => { group = "vpn", protocol = "udp", port = var.vpn_port, cidr = cidr }
    },
  ) : name => merge(local.rule_peers, rule) }

  # Nothing goes out of RDS. Packages come over HTTPS: Amazon Linux's repositories and PyPI.
  egress_rules = { for name, rule in {
    alb_http_to_app    = { group = "alb", protocol = "tcp", port = 80, peer = "app" }
    app_postgres_to_db = { group = "app", protocol = "tcp", port = 5432, peer = "db" }
    # Already covered by app_https_to_internet. It is the rule that stays once a pre-built image
    # makes the downloads at deploy time, and with them that rule, go away.
    app_https_to_s3       = { group = "app", protocol = "tcp", port = 443, prefix_list = aws_vpc_endpoint.s3.prefix_list_id }
    app_https_to_internet = { group = "app", protocol = "tcp", port = 443, cidr = "0.0.0.0/0" }
    vpn_ssh_to_app        = { group = "vpn", protocol = "tcp", port = 22, peer = "app" }
    vpn_postgres_to_db    = { group = "vpn", protocol = "tcp", port = 5432, peer = "db" }
    # Its packages, and Parameter Store for its keys.
    vpn_https_to_internet = { group = "vpn", protocol = "tcp", port = 443, cidr = "0.0.0.0/0" }
  } : name => merge(local.rule_peers, rule) }
}

resource "aws_vpc_security_group_ingress_rule" "all" {
  for_each = local.ingress_rules

  security_group_id            = local.security_group_ids[each.value.group]
  description                  = replace(each.key, "_", " ")
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = each.value.peer == null ? null : local.security_group_ids[each.value.peer]
  cidr_ipv4                    = each.value.cidr
  prefix_list_id               = each.value.prefix_list

  # The emulator gives a peer group back as "<account>/sg-...", AWS's form for another
  # account's group, because the provider here doesn't ask for its own account id
  # (versions.tf). Every plan would then change the rule. tests/network.tftest.hcl checks
  # each rule's peer from this file instead.
  lifecycle {
    ignore_changes = [referenced_security_group_id]
  }
}

resource "aws_vpc_security_group_egress_rule" "all" {
  for_each = local.egress_rules

  security_group_id            = local.security_group_ids[each.value.group]
  description                  = replace(each.key, "_", " ")
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = each.value.peer == null ? null : local.security_group_ids[each.value.peer]
  cidr_ipv4                    = each.value.cidr
  prefix_list_id               = each.value.prefix_list

  # The emulator gives a peer group back as "<account>/sg-...", AWS's form for another
  # account's group, because the provider here doesn't ask for its own account id
  # (versions.tf). Every plan would then change the rule. tests/network.tftest.hcl checks
  # each rule's peer from this file instead.
  lifecycle {
    ignore_changes = [referenced_security_group_id]
  }
}
