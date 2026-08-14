output "url" {
  description = "URL for the clusterkeep-ui UI once DNS/hosts is configured."
  value       = "https://${var.ingress_hostname}"
}

output "etc_hosts_note" {
  description = "Reminder to map the hostname to a worker node IP."
  value       = "Add to /etc/hosts: '<worker-node-ip> ${var.ingress_hostname}' (ingress-nginx runs as a DaemonSet with hostNetwork on the worker nodes)."
}
