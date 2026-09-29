output "ipv4" {
  description = "Öffentliche IPv4-Adresse des Sensors."
  value       = hcloud_server.sensor.ipv4_address
}

output "ipv6" {
  description = "Öffentliche IPv6-Adresse des Sensors."
  value       = hcloud_server.sensor.ipv6_address
}

output "ssh" {
  description = "Befehl für den Admin-Login."
  value       = "ssh -i ~/.ssh/hp_sensor -p 22022 tom@${hcloud_server.sensor.ipv4_address}"
}
