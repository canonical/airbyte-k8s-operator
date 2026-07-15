# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.temporal_admin_k8s.name
}

output "application" {
  description = "The deployed application resource."
  value       = juju_application.temporal_admin_k8s
}

output "provides" {
  description = "Map of the charm's `provides` integration endpoints."
  value = {
    admin              = "admin"
    temporal_host_info = "temporal-host-info"
  }
}
