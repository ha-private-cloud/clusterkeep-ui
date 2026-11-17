output "url" {
  description = "URL for the clusterkeep-ui UI once DNS/hosts is configured."
  value       = "https://${var.ingress_hostname}"
}

output "invite_code" {
  description = "Invite code for the /join page. Rotate with: tofu apply -replace=random_password.invite_code"
  value       = random_password.invite_code.result
  sensitive   = true
}
