terraform {
  required_version = ">= 1.12.0, < 2.0.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.69"
    }
  }
}

# Das API-Token kommt ausschließlich aus der Umgebungsvariable HCLOUD_TOKEN.
# Es gibt bewusst kein token-Argument und keine Variable dafür. So kann das
# Token weder in *.tfvars noch im Repo noch im State landen.
provider "hcloud" {}
