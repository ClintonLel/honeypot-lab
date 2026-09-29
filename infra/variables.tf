variable "admin_source_ips" {
  description = "Quell-Adressen (CIDR), die Admin-SSH auf Port 22022 erreichen dürfen."
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]

  validation {
    condition     = length(var.admin_source_ips) > 0 && alltrue([for ip in var.admin_source_ips : can(cidrhost(ip, 0))])
    error_message = "admin_source_ips braucht mindestens einen Eintrag, jeder im CIDR-Format (z.B. 203.0.113.4/32)."
  }
}
