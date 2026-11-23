output "urls" {
  description = "The guestbook, through the load balancer. It answers once Ansible has run. The HTTP URL only redirects to the HTTPS one."
  value = {
    http  = "http://localhost:${var.listener_port}/"
    https = "https://localhost:${var.https_listener_port}/"
  }
}

output "instance" {
  description = "The EC2 instance. Its container is named floci-aws-ec2-<id>."
  value = {
    id         = aws_instance.app.id
    private_ip = aws_instance.app.private_ip
  }
}

output "database" {
  description = "The RDS instance, as the EC2 instance reaches it and from this machine."
  value = {
    endpoint  = "${aws_db_instance.guestbook.address}:${aws_db_instance.guestbook.port}"
    from_host = "psql -h 127.0.0.1 -p ${var.database_host_port} -U ${var.database_username} guestbook"
  }
}

output "vpn" {
  description = "The VPN server, and the profiles Terraform wrote for vpn_clients. In the emulator only the deploy's profile can connect (variables.tf, vpn_public_host)."
  value = {
    id         = aws_instance.vpn.id
    private_ip = aws_instance.vpn.private_ip
    public_ip  = aws_eip_association.vpn.public_ip
    profiles   = [for name in var.vpn_clients : ".generated/vpn/${name}.ovpn"]
  }
}

output "network" {
  description = "The VPC and its subnets."
  value = {
    vpc_id  = aws_vpc.guestbook.id
    subnets = { for name, subnet in aws_subnet.all : name => subnet.id }
  }
}

output "containers" {
  description = "The Docker container behind each instance, by role. Floci names them floci-aws-ec2-<instance id>, and has no setting to change that."
  value = {
    app = "floci-aws-ec2-${aws_instance.app.id}"
    vpn = "floci-aws-ec2-${aws_instance.vpn.id}"
  }
}
