"""Lightweight ACME client for obtaining Let's Encrypt certificates."""

from acme_client.client import CertResult, obtain_certificate

__all__ = ["CertResult", "obtain_certificate"]
