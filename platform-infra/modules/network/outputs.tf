output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  value      = values(aws_subnet.private)[*].id
  depends_on = [aws_route_table_association.private]
}
