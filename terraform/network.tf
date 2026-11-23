# The guestbook's own network. Nothing in it is reachable from the internet but the load
# balancer and the VPN server (vpn.tf), both in the public subnets.
#
#   public  the load balancer, the NAT gateway, the VPN server   out through the internet gateway
#   app     the instance, no public address                      out through the NAT gateway; S3 through its endpoint
#   data    RDS                                                  nothing out: local routes only
#
# Two zones, because the load balancer and the DB subnet group need two.
#
# The emulator records all of this and enforces none of it (docs/floci.md, section 5).
# tests/network.tftest.hcl checks the rules instead.

locals {
  zones = {
    a = "${data.aws_region.current.region}a"
    b = "${data.aws_region.current.region}b"
  }
  # Each tier's first /24 in the VPC: public 10.0.0.0/24 and 10.0.1.0/24, app 10.0.10.0/24...
  tier_netnums = { public = 0, app = 10, data = 20 }
  subnets = merge([
    for tier, netnum in local.tier_netnums : {
      for i, zone in keys(local.zones) : "${tier}-${zone}" => {
        tier = tier
        zone = local.zones[zone]
        cidr = cidrsubnet(var.vpc_cidr, 8, netnum + i)
      }
    }
  ]...)
}

resource "aws_vpc" "guestbook" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "guestbook"
  }
}

resource "aws_subnet" "all" {
  for_each          = local.subnets
  vpc_id            = aws_vpc.guestbook.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.zone

  tags = {
    Name = "guestbook-${each.key}"
  }
}

resource "aws_internet_gateway" "guestbook" {
  vpc_id = aws_vpc.guestbook.id
}

# One NAT gateway: the instance downloads its packages at deploy time. If its zone fails, the
# downloads stop, not the app.
resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "guestbook" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.all["public-a"].id
  depends_on    = [aws_internet_gateway.guestbook]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.guestbook.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.guestbook.id
  }
}

resource "aws_route_table" "app" {
  vpc_id = aws_vpc.guestbook.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.guestbook.id
  }
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.guestbook.id
}

resource "aws_route_table_association" "all" {
  for_each       = local.subnets
  subnet_id      = aws_subnet.all[each.key].id
  route_table_id = local.route_table_ids[each.value.tier]
}

locals {
  route_table_ids = {
    public = aws_route_table.public.id
    app    = aws_route_table.app.id
    data   = aws_route_table.data.id
  }
}

# S3 from the app subnets without the NAT gateway. The app's role may use the bucket only
# through this endpoint (main.tf).
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.guestbook.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.app.id]
}
