# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Name of the application in the Juju model."
  type        = string
  default     = "airbyte-k8s"
}

variable "base" {
  description = "The operating system on which to deploy."
  type        = string
  default     = "ubuntu@22.04"
}

variable "channel" {
  description = "The channel to use when deploying the charm."
  type        = string
  default     = "latest/edge"
}

variable "config" {
  description = "Application configuration. Options at https://charmhub.io/airbyte-k8s/configurations."
  type = object({
    log-level                                                 = optional(string)
    temporal-host                                             = optional(string)
    secret-persistence                                        = optional(string)
    secret-store-gcp-project-id                               = optional(string)
    gcp-credentials-secret-id                                 = optional(string)
    vault-address                                             = optional(string)
    vault-prefix                                              = optional(string)
    vault-token-secret-id                                     = optional(string)
    vault-auth-method                                         = optional(string)
    aws-credentials-secret-id                                 = optional(string)
    aws-kms-key-arn                                           = optional(string)
    aws-secret-manager-secret-tags                            = optional(string)
    sync-job-retries-complete-failures-max-successive         = optional(number)
    sync-job-retries-complete-failures-max-total              = optional(number)
    sync-job-retries-complete-failures-backoff-min-interval-s = optional(number)
    sync-job-retries-complete-failures-backoff-max-interval-s = optional(number)
    sync-job-retries-complete-failures-backoff-base           = optional(number)
    sync-job-retries-partial-failures-max-successive          = optional(number)
    sync-job-retries-partial-failures-max-total               = optional(number)
    sync-job-max-timeout-days                                 = optional(number)
    job-main-container-cpu-request                            = optional(string)
    job-main-container-cpu-limit                              = optional(string)
    job-main-container-memory-request                         = optional(string)
    job-main-container-memory-limit                           = optional(string)
    max-fields-per-connections                                = optional(number)
    max-days-of-only-failed-jobs-before-connection-disable    = optional(number)
    max-failed-jobs-in-a-row-before-connection-disable        = optional(number)
    max-spec-workers                                          = optional(number)
    max-check-workers                                         = optional(number)
    max-sync-workers                                          = optional(number)
    max-discover-workers                                      = optional(number)
    temporal-history-retention-in-days                        = optional(number)
    job-kube-tolerations                                      = optional(string)
    job-kube-node-selectors                                   = optional(string)
    job-kube-annotations                                      = optional(string)
    job-kube-main-container-image-pull-policy                 = optional(string)
    job-kube-main-container-image-pull-secret                 = optional(string)
    job-kube-sidecar-container-image-pull-policy              = optional(string)
    job-kube-socat-image                                      = optional(string)
    job-kube-busybox-image                                    = optional(string)
    job-kube-curl-image                                       = optional(string)
    job-kube-namespace                                        = optional(string)
    spec-job-kube-node-selectors                              = optional(string)
    check-job-kube-node-selectors                             = optional(string)
    discover-job-kube-node-selectors                          = optional(string)
    spec-job-kube-annotations                                 = optional(string)
    check-job-kube-annotations                                = optional(string)
    discover-job-kube-annotations                             = optional(string)
    storage-type                                              = optional(string)
    storage-bucket-logs                                       = optional(string)
    logs-ttl                                                  = optional(number)
    storage-bucket-state                                      = optional(string)
    storage-bucket-activity-payload                           = optional(string)
    storage-bucket-workload-output                            = optional(string)
    storage-bucket-audit-logging                              = optional(string)
    pod-running-ttl-minutes                                   = optional(number)
    pod-successful-ttl-minutes                                = optional(number)
    pod-unsuccessful-ttl-minutes                              = optional(number)
  })
  default = {}
}

variable "constraints" {
  description = "Juju constraints to apply for this application."
  type        = string
  default     = null
}

variable "model_uuid" {
  description = "Reference to the `juju_model` UUID to deploy to."
  type        = string
}

variable "resources" {
  description = "Map of OCI-image resources (airbyte-image) to use instead of the charm's bundled image."
  type        = map(string)
  default     = {}
}

variable "revision" {
  description = "Revision number of the charm to deploy. Null deploys the latest revision on the channel."
  type        = number
  default     = null
}

variable "trust" {
  description = "Whether the application can access cluster-wide Kubernetes resources. Airbyte requires this to read its auth secret via the Kubernetes API."
  type        = bool
  default     = true
}

variable "units" {
  description = "Number of units to deploy."
  type        = number
  default     = 1
}
