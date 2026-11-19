output "urls" {
  description = "The guestbook, through the load balancer. It answers once Ansible has run."
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
