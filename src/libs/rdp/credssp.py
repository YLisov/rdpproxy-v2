"""CredSSP/NTLM authentication against RDP backend (1:1 port from v1)."""

from __future__ import annotations

import asyncio
import logging
import ssl
import struct
from dataclasses import dataclass
from struct import pack

from cryptography import x509 as cx509
from cryptography.hazmat.primitives import serialization
from impacket import ntlm
from impacket.spnego import (
    SPNEGO_NegTokenInit,
    SPNEGO_NegTokenResp,
    SPNEGOCipher,
    TypesMech,
    asn1encode,
)

from rdp.constants import (
    ASN1_CONTEXT_0,
    ASN1_CONTEXT_1,
    ASN1_CONTEXT_2,
    ASN1_CONTEXT_3,
    ASN1_INTEGER,
    ASN1_OCTET_STR,
    ASN1_SEQUENCE,
    MAX_CREDSSP_RECORD_LEN,
    REQUESTED_PROTOCOLS_HYBRID,
    TPKT_VERSION,
)

logger = logging.getLogger("rdpproxy.credssp")
NTLM_MECH_OID = TypesMech["NTLMSSP - Microsoft NTLM Security Support Provider"]


def _extract_raw_pubkey(spki_der: bytes) -> bytes:
    """Extract raw public key bytes from SubjectPublicKeyInfo DER, skipping AlgorithmIdentifier."""
    if not spki_der or spki_der[0] != 0x30:
        raise ValueError("Expected SEQUENCE tag in SPKI")
    offset = 2
    if spki_der[1] & 0x80:
        n_len_bytes = spki_der[1] & 0x7F
        offset += n_len_bytes
    # skip AlgorithmIdentifier (SEQUENCE)
    if spki_der[offset] != 0x30:
        raise ValueError("Expected AlgorithmIdentifier SEQUENCE")
    algo_len_byte = spki_der[offset + 1]
    if algo_len_byte & 0x80:
        n = algo_len_byte & 0x7F
        algo_len = int.from_bytes(spki_der[offset + 2 : offset + 2 + n], "big")
        offset += 2 + n + algo_len
    else:
        offset += 2 + algo_len_byte
    # BIT STRING containing the public key
    if spki_der[offset] != 0x03:
        raise ValueError("Expected BIT STRING tag")
    offset += 1
    bit_len_byte = spki_der[offset]
    offset += 1
    if bit_len_byte & 0x80:
        n = bit_len_byte & 0x7F
        offset += n
    offset += 1  # skip unused-bits byte
    return spki_der[offset:]


# ── TSRequest DER encoder/decoder ──

class TSRequest:
    """CredSSP TSRequest – minimal hand-coded ASN.1 DER encoder/decoder."""

    def __init__(self, data: bytes | None = None):
        self.fields: dict = {}
        if data:
            self.from_string(data)

    def __setitem__(self, key, value):
        self.fields[key] = value

    def __getitem__(self, key):
        return self.fields[key]

    def __contains__(self, key):
        return key in self.fields

    def from_string(self, data: bytes) -> None:
        if data[0] != ASN1_SEQUENCE:
            raise ValueError(f"TSRequest: expected SEQUENCE tag 0x{ASN1_SEQUENCE:02x}, got 0x{data[0]:02x}")
        inner, _ = _asn1decode(data[1:])
        data = inner
        while data:
            tag = data[0]
            data = data[1:]
            content, consumed = _asn1decode(data)
            data = data[consumed:]
            if tag == ASN1_CONTEXT_0:
                pass
            elif tag == ASN1_CONTEXT_1:
                self.fields["NegoData"] = _extract_octet_from_nego_data(content)
            elif tag == ASN1_CONTEXT_2:
                if content[0] == ASN1_OCTET_STR:
                    payload, _ = _asn1decode(content[1:])
                    self.fields["authInfo"] = payload
            elif tag == ASN1_CONTEXT_3:
                if content[0] == ASN1_OCTET_STR:
                    payload, _ = _asn1decode(content[1:])
                    self.fields["pubKeyAuth"] = payload

    def get_data(self) -> bytes:
        version_blob = pack("B", ASN1_CONTEXT_0) + asn1encode(pack("B", ASN1_INTEGER) + asn1encode(pack("B", 2)))
        nego_blob = b""
        if "NegoData" in self.fields:
            nego_blob = (
                pack("B", ASN1_CONTEXT_1)
                + asn1encode(
                    pack("B", ASN1_SEQUENCE)
                    + asn1encode(
                        pack("B", ASN1_SEQUENCE)
                        + asn1encode(pack("B", ASN1_CONTEXT_0) + asn1encode(pack("B", ASN1_OCTET_STR) + asn1encode(self.fields["NegoData"])))
                    )
                )
            )
        auth_blob = b""
        if "authInfo" in self.fields:
            auth_blob = pack("B", ASN1_CONTEXT_2) + asn1encode(pack("B", ASN1_OCTET_STR) + asn1encode(self.fields["authInfo"]))
        pubkey_blob = b""
        if "pubKeyAuth" in self.fields:
            pubkey_blob = pack("B", ASN1_CONTEXT_3) + asn1encode(pack("B", ASN1_OCTET_STR) + asn1encode(self.fields["pubKeyAuth"]))
        inner = version_blob + nego_blob + auth_blob + pubkey_blob
        return pack("B", ASN1_SEQUENCE) + asn1encode(inner)


class TSPasswordCreds:
    def __init__(self):
        self.fields: dict = {}

    def __setitem__(self, k, v):
        self.fields[k] = v

    def get_data(self) -> bytes:
        def field(ctx_tag: int, value_bytes: bytes) -> bytes:
            return pack("B", 0xA0 + ctx_tag) + asn1encode(pack("B", ASN1_OCTET_STR) + asn1encode(value_bytes))

        inner = field(0, self.fields["domainName"]) + field(1, self.fields["userName"]) + field(2, self.fields["password"])
        return pack("B", ASN1_SEQUENCE) + asn1encode(inner)


class TSCredentials:
    def __init__(self):
        self.fields: dict = {}

    def __setitem__(self, k, v):
        self.fields[k] = v

    def get_data(self) -> bytes:
        cred_type_blob = pack("B", 0xA0) + asn1encode(pack("B", ASN1_INTEGER) + asn1encode(pack("B", self.fields["credType"])))
        creds_blob = pack("B", 0xA1) + asn1encode(pack("B", ASN1_OCTET_STR) + asn1encode(self.fields["credentials"]))
        return pack("B", ASN1_SEQUENCE) + asn1encode(cred_type_blob + creds_blob)


# ── ASN.1 helpers ──

def _asn1decode(data: bytes) -> tuple[bytes, int]:
    if not data:
        return b"", 0
    length_byte = data[0]
    if length_byte & 0x80:
        num = length_byte & 0x7F
        length = int.from_bytes(data[1 : 1 + num], "big")
        offset = 1 + num
    else:
        length = length_byte
        offset = 1
    return data[offset : offset + length], offset + length


def _extract_octet_from_nego_data(raw: bytes) -> bytes:
    if raw[0] != ASN1_SEQUENCE:
        return raw
    inner, _ = _asn1decode(raw[1:])
    if not inner or inner[0] != ASN1_SEQUENCE:
        return inner or raw
    inner2, _ = _asn1decode(inner[1:])
    if not inner2 or inner2[0] != ASN1_CONTEXT_0:
        return inner2 or inner
    inner3, _ = _asn1decode(inner2[1:])
    if inner3 and inner3[0] == ASN1_OCTET_STR:
        payload, _ = _asn1decode(inner3[1:])
        return payload
    return inner3


# ── Transport helpers ──

def _build_tpkt(payload: bytes) -> bytes:
    return bytes([TPKT_VERSION, 0]) + struct.pack(">H", len(payload) + 4) + payload


def _build_x224_cr(requested_protocols: int) -> bytes:
    x224 = b"\x0e\xe0\x00\x00\x00\x00\x00"
    rdp_neg_req = b"\x01\x00\x08\x00" + struct.pack("<I", requested_protocols)
    return _build_tpkt(x224 + rdp_neg_req)


async def _read_tpkt(reader: asyncio.StreamReader) -> bytes:
    header = await reader.readexactly(4)
    if header[0] != TPKT_VERSION:
        raise ValueError("Invalid TPKT version from backend")
    total_len = struct.unpack(">H", header[2:4])[0]
    return await reader.readexactly(total_len - 4)


async def _read_credssp_record(reader: asyncio.StreamReader) -> bytes:
    first = await reader.readexactly(1)
    if first[0] == TPKT_VERSION:
        rest = await reader.readexactly(3)
        total_len = struct.unpack(">H", rest[2:4])[0]
        return await reader.readexactly(total_len - 4)
    if first[0] != 0x30:
        raise ValueError(f"Unexpected CredSSP record tag: 0x{first[0]:02x}")
    len_b = await reader.readexactly(1)
    header = first + len_b
    if len_b[0] & 0x80:
        ll = len_b[0] & 0x7F
        len_ext = await reader.readexactly(ll)
        header += len_ext
        plen = int.from_bytes(len_ext, "big")
    else:
        plen = len_b[0]
    if plen > MAX_CREDSSP_RECORD_LEN:
        raise ValueError(f"CredSSP record too large: {plen} bytes")
    payload = await reader.readexactly(plen)
    return header + payload


# ── SPNEGO wrappers ──

def _split_domain_user(username: str, fallback_domain: str) -> tuple[str, str]:
    if "\\" in username:
        domain, user = username.split("\\", 1)
        return domain, user
    if "@" in username:
        user, domain = username.split("@", 1)
        return domain, user
    domain = fallback_domain
    if "." in domain:
        domain = domain.split(".", 1)[0]
    return domain.upper(), username


def _build_spnego_init(ntlm_type1: bytes) -> bytes:
    token = SPNEGO_NegTokenInit()
    token["MechTypes"] = [NTLM_MECH_OID]
    token["MechToken"] = ntlm_type1
    return token.getData()


def _build_spnego_resp(ntlm_type3: bytes) -> bytes:
    token = SPNEGO_NegTokenResp()
    token["ResponseToken"] = ntlm_type3
    return token.getData()


def _extract_ntlm_from_resp(nego_data: bytes) -> bytes:
    if nego_data.startswith(b"NTLMSSP\x00"):
        return nego_data
    try:
        resp = SPNEGO_NegTokenResp(nego_data)
        return resp["ResponseToken"]
    except Exception:
        return nego_data


# ── Main entry ──

@dataclass
class BackendConnection:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter


async def connect_and_authenticate(
    *, target_host: str, target_port: int, username: str, password: str, fallback_domain: str,
) -> BackendConnection:
    """Full CredSSP/NTLM handshake against backend RDP server. Returns connected streams."""
    logger.info("Connecting backend %s:%s for user=%s", target_host, target_port, username)
    reader, writer = await asyncio.open_connection(target_host, target_port)

    writer.write(_build_x224_cr(REQUESTED_PROTOCOLS_HYBRID))
    await writer.drain()
    x224_cc = await _read_tpkt(reader)
    selected_protocol = None
    marker = x224_cc.find(b"\x02\x00\x08\x00")
    if marker != -1 and marker + 8 <= len(x224_cc):
        selected_protocol = struct.unpack_from("<I", x224_cc, marker + 4)[0]
    logger.info(
        "Backend X.224 negotiation complete%s",
        f" selectedProtocol=0x{selected_protocol:08x}" if selected_protocol is not None else "",
    )

    tls_ctx = ssl.create_default_context()
    tls_ctx.check_hostname = False
    tls_ctx.verify_mode = ssl.CERT_NONE
    await writer.start_tls(tls_ctx, server_hostname=target_host)
    logger.info("Backend TLS established")

    domain, user = _split_domain_user(username, fallback_domain)
    logger.info("CredSSP NTLM identity: domain=%r user=%r", domain, user)

    auth = ntlm.getNTLMSSPType1("", "", True, use_ntlmv2=True)
    ts1 = TSRequest()
    ts1["NegoData"] = _build_spnego_init(auth.getData())
    writer.write(ts1.get_data())
    await writer.drain()

    buff = await _read_credssp_record(reader)
    ts_resp = TSRequest(buff)
    challenge_raw = _extract_ntlm_from_resp(ts_resp["NegoData"])
    logger.info("Received NTLM challenge from backend")

    type3, exported_session_key = ntlm.getNTLMSSPType3(auth, challenge_raw, user, password, domain, "", "", use_ntlmv2=True)

    ssl_obj = writer.get_extra_info("ssl_object")
    cert_der = ssl_obj.getpeercert(binary_form=True)
    cert = cx509.load_der_x509_certificate(cert_der)
    spki_der = cert.public_key().public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    server_pub_key = _extract_raw_pubkey(spki_der)

    cipher = SPNEGOCipher(type3["flags"], exported_session_key)
    signature, cripted_key = cipher.encrypt(server_pub_key)

    ts3 = TSRequest()
    ts3["NegoData"] = _build_spnego_resp(type3.getData())
    ts3["pubKeyAuth"] = signature.getData() + cripted_key
    writer.write(ts3.get_data())
    await writer.drain()
    logger.info("Sent NTLM Type3 (SPNEGO-wrapped) + pubKeyAuth")

    try:
        buff = await asyncio.wait_for(_read_credssp_record(reader), timeout=5.0)
        ts_srv = TSRequest(buff)
        if "pubKeyAuth" in ts_srv:
            logger.info("Server pubKeyAuth echo received (OK)")
    except TimeoutError:
        logger.info("No pubKeyAuth echo from server (continuing)")
    except Exception as exc:
        logger.warning("pubKeyAuth echo read failed: %s", exc)

    tsp = TSPasswordCreds()
    tsp["domainName"] = domain.encode("utf-16-le")
    tsp["userName"] = user.encode("utf-16-le")
    tsp["password"] = password.encode("utf-16-le")

    tsc = TSCredentials()
    tsc["credType"] = 1
    tsc["credentials"] = tsp.get_data()

    sig2, cripted_creds = cipher.encrypt(tsc.get_data())
    ts5 = TSRequest()
    ts5["authInfo"] = sig2.getData() + cripted_creds
    writer.write(ts5.get_data())
    await writer.drain()
    logger.info("Sent encrypted TSCredentials — CredSSP complete")

    try:
        await asyncio.wait_for(_read_credssp_record(reader), timeout=2.0)
        logger.info("CredSSP post-auth response received")
    except TimeoutError:
        logger.debug("No CredSSP post-auth response (continuing to MCS relay)")
    except Exception as exc:
        logger.warning("CredSSP post-auth read failed: %s", exc)

    return BackendConnection(reader=reader, writer=writer)
