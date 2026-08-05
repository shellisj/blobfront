variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
  default     = "rg-blobfront"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "uksouth"
}

variable "vm_size" {
  # B1ls (0.5 GiB RAM) is the cheapest burstable SKU and is viable now that the
  # image is prebuilt in CI — the VM only pulls it, it never compiles Caddy. If
  # the container is OOM-killed under load, bump to Standard_B1s (1 GiB) or the
  # newer Standard_B2ts_v2 (1 GiB, cheaper than B1s). Set this in terraform.tfvars.
  description = "VM size. B1ls (0.5 GiB) is cheapest; B1s/B2ts_v2 (1 GiB) are safer."
  type        = string
  default     = "Standard_B1ls"
}

variable "admin_username" {
  description = "SSH admin username"
  type        = string
  default     = "blobfront"
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key for VM access"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the VM (set to your IP)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    project = "blobfront"
    managed = "terraform"
  }
}
