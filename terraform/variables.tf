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
  description = "VM size (B1s is cheapest)"
  type        = string
  default     = "Standard_B1s"
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
