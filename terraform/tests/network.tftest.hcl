# What the network must let through, and what it must not. The emulator records security groups,
# subnets and routes and enforces none of them, so this test is what checks them.
#
#   terraform test        # from terraform/: no emulator needed
#
# Everything AWS is mocked, and so are the files for Ansible: the test makes no call and
# writes nothing, so it leaves a running stack's .generated/ alone. The tls and random
# providers run for real: they work locally. "apply" rather than "plan", so that the mocked
# ids are known and the rules can be compared with the groups they name.

# The provider checks that an ARN it is handed looks like one, so the mocks make them so.
mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "us-east-1"
    }
  }

  mock_resource "aws_lb" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/guestbook/0"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/guestbook-app/0"
    }
  }

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/0"
    }
  }
}

mock_provider "local" {}

run "only_the_load_balancer_and_the_vpn_take_traffic_from_the_internet" {
  command = apply

  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.all :
      rule.cidr_ipv4 == null || contains([aws_security_group.alb.id, aws_security_group.vpn.id], rule.security_group_id)
    ])
    error_message = "Only guestbook-alb and guestbook-vpn may take anything from an address range."
  }

  assert {
    condition = toset([
      for rule in aws_vpc_security_group_ingress_rule.all : "${rule.ip_protocol}/${rule.from_port}"
      if rule.security_group_id == aws_security_group.alb.id
    ]) == toset(["tcp/8443", "tcp/8080"])
    error_message = "The load balancer takes its two listeners' ports, and nothing else."
  }

  assert {
    condition = toset([
      for rule in aws_vpc_security_group_ingress_rule.all : "${rule.ip_protocol}/${rule.from_port}"
      if rule.security_group_id == aws_security_group.vpn.id
    ]) == toset(["udp/1194"])
    error_message = "The VPN server takes its UDP port and nothing else: no SSH from anywhere."
  }
}

run "ssh_and_postgres_come_only_from_their_peers" {
  command = apply

  assert {
    condition = toset([
      for rule in aws_vpc_security_group_ingress_rule.all : rule.referenced_security_group_id
      if rule.from_port == 22
    ]) == toset([aws_security_group.vpn.id])
    error_message = "Port 22 opens only to guestbook-vpn."
  }

  assert {
    condition = toset([
      for rule in aws_vpc_security_group_ingress_rule.all : rule.referenced_security_group_id
      if rule.from_port == 5432
    ]) == toset([aws_security_group.app.id, aws_security_group.vpn.id])
    error_message = "PostgreSQL opens only to guestbook-app and guestbook-vpn."
  }

  assert {
    condition = toset([
      for rule in aws_vpc_security_group_ingress_rule.all : "${rule.from_port}<-${rule.referenced_security_group_id}"
      if rule.security_group_id == aws_security_group.app.id
    ]) == toset(["80<-${aws_security_group.alb.id}", "22<-${aws_security_group.vpn.id}"])
    error_message = "The instance takes HTTP from the load balancer and SSH from the VPN server, nothing else."
  }

  assert {
    condition = length([
      for rule in aws_vpc_security_group_egress_rule.all : rule
      if rule.security_group_id == aws_security_group.db.id
    ]) == 0
    error_message = "Nothing goes out of RDS."
  }
}

run "the_instance_and_the_database_have_no_public_address" {
  command = apply

  assert {
    condition     = aws_instance.app.associate_public_ip_address == false && aws_instance.app.subnet_id == aws_subnet.all["app-a"].id
    error_message = "The instance sits in an app subnet, with no public address."
  }

  assert {
    condition     = aws_db_instance.guestbook.publicly_accessible == false
    error_message = "RDS is not publicly accessible."
  }

  assert {
    condition     = toset(aws_db_subnet_group.guestbook.subnet_ids) == toset([aws_subnet.all["data-a"].id, aws_subnet.all["data-b"].id])
    error_message = "RDS is in the data subnets only."
  }

  assert {
    condition     = aws_lb.guestbook.internal == false && toset(aws_lb.guestbook.subnets) == toset([aws_subnet.all["public-a"].id, aws_subnet.all["public-b"].id])
    error_message = "The load balancer faces the internet, from the public subnets."
  }

  assert {
    condition     = length(aws_route_table.data.route) == 0
    error_message = "The data subnets have no way out."
  }

  assert {
    condition     = one(aws_route_table.app.route).nat_gateway_id == aws_nat_gateway.guestbook.id
    error_message = "The app subnets go out through the NAT gateway only."
  }
}

run "the_pictures_are_reachable_only_through_the_vpc_endpoint" {
  command = apply

  assert {
    condition     = jsondecode(aws_iam_role_policy.pictures.policy).Statement[0].Condition.StringEquals["aws:SourceVpce"] == aws_vpc_endpoint.s3.id
    error_message = "The app's role may use the bucket only through the VPC's S3 endpoint."
  }
}

run "the_vpn_server_keeps_its_secrets_out_of_its_user_data" {
  command = apply

  assert {
    condition     = !strcontains(local.vpn_user_data, "PRIVATE KEY") && !strcontains(local.vpn_user_data, "OpenVPN Static key")
    error_message = "The VPN server's user data must hold no private key and no tls-crypt key: they come from Parameter Store."
  }

  assert {
    condition = toset(jsondecode(aws_iam_role_policy.vpn_secrets.policy).Statement[0].Resource) == toset([
      aws_ssm_parameter.vpn_server_key.arn, aws_ssm_parameter.vpn_tls_crypt_key.arn,
    ])
    error_message = "The VPN server's role may read its two parameters and nothing else."
  }

  assert {
    condition     = aws_ssm_parameter.vpn_server_key.type == "SecureString" && aws_ssm_parameter.vpn_tls_crypt_key.type == "SecureString"
    error_message = "The VPN's secrets are stored encrypted."
  }
}

run "the_vpn_refuses_whoever_is_not_listed" {
  command = apply

  variables {
    vpn_clients = ["ansible", "ana"]
  }

  assert {
    condition     = strcontains(local.vpn_server_conf, "\nccd-exclusive\n") && strcontains(local.vpn_server_conf, "\ntls-crypt ")
    error_message = "The server takes only clients with a ccd file, and only packets with the tls-crypt key."
  }

  assert {
    condition     = toset(keys(local_sensitive_file.vpn_profile)) == toset(["ansible", "ana"])
    error_message = "There is one profile per name in vpn_clients."
  }

  assert {
    condition     = strcontains(local.vpn_profiles["ansible"], "\nroute-nopull\n") && !strcontains(local.vpn_profiles["ana"], "route-nopull")
    error_message = "In the emulator the deploy's profile routes the app's address only; a person's takes the pushed routes."
  }
}

run "the_deploy_client_must_stay" {
  command = plan

  variables {
    vpn_clients = ["ana"]
  }

  expect_failures = [var.vpn_clients]
}
