"""ACME client for obtaining Let's Encrypt certificates using the ``acme`` library."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import josepy as jose
from acme import challenges, client as acme_client, errors as acme_errors, messages
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.hashes import SHA256

from acme_client.challenge_server import ChallengeServer

logger = logging.getLogger("rdpproxy.acme")

LETS_ENCRYPT_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
LETS_ENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"


@dataclass
class CertResult:
    success: bool
    domain: str = ""
    message: str = ""
    fullchain_path: str = ""
    privkey_path: str = ""
    haproxy_pem_path: str = ""
    error: str = ""


def _load_or_create_account_key(path: str) -> jose.JWKRSA:
    """Load existing account key or generate a new RSA-2048 one."""
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                key = serialization.load_pem_private_key(f.read(), password=None)
            return jose.JWKRSA(key=key)
        except (ValueError, TypeError) as exc:
            logger.warning("Corrupt account key at %s (%s), regenerating", path, exc)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pem)
    return jose.JWKRSA(key=key)


def _generate_domain_key_and_csr(domain: str) -> tuple[bytes, bytes]:
    """Generate a fresh EC P-256 private key and CSR for the domain."""
    key = ec.generate_private_key(ec.SECP256R1())
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .sign(key, SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    return key_pem, csr_pem


def _obtain_sync(
    domain: str,
    email: str | None,
    certs_dir: str,
    acme_directory: str,
    challenge_server: ChallengeServer,
    loop: asyncio.AbstractEventLoop,
) -> CertResult:
    """Blocking ACME flow (runs in a thread, coordinates with asyncio challenge server)."""

    account_key_path = os.path.join(certs_dir, "account.key")
    account_key = _load_or_create_account_key(account_key_path)

    net = acme_client.ClientNetwork(account_key, user_agent="rdpproxy-acme/1.0")
    directory = messages.Directory.from_json(net.get(acme_directory).json())
    acme = acme_client.ClientV2(directory, net=net)

    try:
        regr = acme.new_account(
            messages.NewRegistration.from_data(
                email=email or None,
                terms_of_service_agreed=True,
            )
        )
    except acme_errors.ConflictError as exc:
        regr = acme.query_registration(
            messages.RegistrationResource(
                uri=exc.location,
                body=messages.Registration(),
            )
        )
        logger.info("Using existing ACME account: %s", regr.uri)
    else:
        logger.info("ACME account registered: %s", regr.uri)

    domain_key_pem, csr_pem = _generate_domain_key_and_csr(domain)

    order = acme.new_order(csr_pem)
    logger.info("ACME order created for %s", domain)

    for authzr in order.authorizations:
        for chall_body in authzr.body.challenges:
            if not isinstance(chall_body.chall, challenges.HTTP01):
                continue
            token = chall_body.chall.encode("token")
            key_authz = chall_body.chall.validation(account_key)
            future = asyncio.run_coroutine_threadsafe(
                _set_challenge(challenge_server, token, key_authz), loop
            )
            future.result(timeout=5)
            acme.answer_challenge(chall_body, chall_body.response(account_key))
            logger.info("Answered HTTP-01 challenge for %s", domain)

    deadline = datetime.datetime.now() + datetime.timedelta(seconds=180)
    try:
        order = acme.poll_and_finalize(order, deadline)
    except acme_errors.ValidationError as exc:
        errors_info = "; ".join(
            str(authzr.body.status) for authzr in exc.failed_authzrs
        )
        return CertResult(
            success=False,
            domain=domain,
            error=f"Challenge validation failed: {errors_info}",
            message=f"Certificate order failed: challenge validation error",
        )
    except acme_errors.TimeoutError:
        return CertResult(
            success=False,
            domain=domain,
            error="Timed out waiting for order to become valid",
            message="Certificate order timed out",
        )

    fullchain_pem = order.fullchain_pem.encode() if isinstance(order.fullchain_pem, str) else order.fullchain_pem

    os.makedirs(certs_dir, exist_ok=True)
    fullchain_path = os.path.join(certs_dir, "fullchain.pem")
    privkey_path = os.path.join(certs_dir, "privkey.pem")
    haproxy_pem_path = os.path.join(certs_dir, "rdp.pem")

    with open(fullchain_path, "wb") as f:
        f.write(fullchain_pem)
    with open(privkey_path, "wb") as f:
        f.write(domain_key_pem)
    with open(haproxy_pem_path, "wb") as f:
        f.write(fullchain_pem)
        f.write(domain_key_pem)

    logger.info("Certificate saved: %s, %s, %s", fullchain_path, privkey_path, haproxy_pem_path)
    return CertResult(
        success=True,
        domain=domain,
        message="Certificate obtained successfully",
        fullchain_path=fullchain_path,
        privkey_path=privkey_path,
        haproxy_pem_path=haproxy_pem_path,
    )


async def _set_challenge(server: ChallengeServer, token: str, key_authz: str) -> None:
    server.set_token(token, key_authz)


def cert_days_remaining(certs_dir: str) -> int | None:
    """Return the number of days until the certificate in *certs_dir* expires.

    Returns ``None`` when the certificate file is missing or cannot be parsed.
    """
    fullchain_path = os.path.join(certs_dir, "fullchain.pem")
    try:
        with open(fullchain_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = cert.not_valid_after_utc - now
        return delta.days
    except Exception:
        return None


def cert_needs_renewal(certs_dir: str, renew_before_days: int = 30) -> bool:
    """Return True when the certificate is missing, expired, or expires within *renew_before_days* days."""
    days = cert_days_remaining(certs_dir)
    return days is None or days < renew_before_days


async def obtain_certificate(
    domain: str,
    email: str | None,
    certs_dir: str,
    acme_directory: str = LETS_ENCRYPT_DIRECTORY,
    challenge_port: int = 80,
) -> CertResult:
    """Obtain a certificate from Let's Encrypt via HTTP-01 challenge.

    Starts a temporary HTTP server on *challenge_port*, performs the ACME
    flow in a thread, then shuts down the server.
    """
    challenge_server = ChallengeServer()
    loop = asyncio.get_running_loop()
    try:
        await challenge_server.start(challenge_port)
        result = await loop.run_in_executor(
            None,
            _obtain_sync,
            domain,
            email,
            certs_dir,
            acme_directory,
            challenge_server,
            loop,
        )
        return result
    except Exception as exc:
        logger.exception("ACME certificate request failed for %s", domain)
        return CertResult(
            success=False,
            domain=domain,
            error=str(exc),
            message=f"Certificate request failed: {exc}",
        )
    finally:
        challenge_server.clear_tokens()
        await challenge_server.stop()
