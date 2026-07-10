# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.airbyte_k8s.name
}

output "provides" {
  description = "Map of the charm's `provides` integration endpoints."
  value = {
    airbyte_server    = "airbyte-server"
    grafana_dashboard = "grafana-dashboard"
  }
}

output "requires" {
  description = "Map of the charm's `requires` integration endpoints."
  value = {
    db             = "db"
    object_storage = "object-storage"
    s3_parameters  = "s3-parameters"
    ingress        = "ingress"
    logging        = "logging"
    send_otlp      = "send-otlp"
  }
}
