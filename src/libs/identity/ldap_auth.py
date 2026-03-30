from __future__ import annotations

import ssl
import uuid
from dataclasses import dataclass

from ldap3 import ALL, MODIFY_ADD, MODIFY_DELETE, SUBTREE, Connection, Server, Tls
from ldap3.utils.conv import escape_filter_chars

from config.loader import LdapConfig


@dataclass
class LDAPUserInfo:
    username: str
    user_dn: str
    groups: list[str]
    group_guids: list[str]


class LDAPAuthenticator:
    """LDAP/AD authentication with group resolution and password change support."""

    def __init__(self, cfg: LdapConfig) -> None:
        self.server_host = cfg.server
        self.mode = cfg.mode
        default_port = 636 if self.mode == "ldaps" else 389
        self.server_port = cfg.port or default_port
        self.bind_dn = cfg.bind_dn
        self.bind_password = cfg.bind_password
        self.users_dn = cfg.users_dn
        self.domain = cfg.domain
        tls_verify = cfg.tls_verify
        self._tls = Tls(validate=ssl.CERT_REQUIRED if tls_verify else ssl.CERT_NONE)
        self._base_dn = self._derive_base_dn(self.users_dn)

    @staticmethod
    def _derive_base_dn(users_dn: str) -> str:
        low = users_dn.lower()
        idx = low.find("dc=")
        if idx == -1:
            return users_dn
        return users_dn[idx:]

    @staticmethod
    def _guid_from_ldap_raw(raw: object) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return str(uuid.UUID(bytes_le=bytes(raw)))
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                return None
            try:
                return str(uuid.UUID(s))
            except Exception:
                return None
        return None

    def _resolve_group_guids(self, conn: Connection, group_dns: list[str]) -> list[str]:
        if not group_dns:
            return []
        dn_to_guid: dict[str, str] = {}
        chunk_size = 30
        for i in range(0, len(group_dns), chunk_size):
            chunk = group_dns[i : i + chunk_size]
            or_parts = [f"(distinguishedName={escape_filter_chars(dn)})" for dn in chunk]
            or_filter = "(|" + "".join(or_parts) + ")"
            search_filter = f"(&(objectClass=group){or_filter})"
            conn.search(
                search_base=self._base_dn, search_filter=search_filter,
                search_scope=SUBTREE, attributes=["objectGUID", "distinguishedName"],
                size_limit=len(chunk),
            )
            for entry in conn.entries:
                try:
                    dn_val = str(entry.distinguishedName.value) if "distinguishedName" in entry else str(entry.entry_dn)
                except Exception:
                    dn_val = str(entry.entry_dn)
                guid_raw = entry.objectGUID.value if "objectGUID" in entry else None
                guid = self._guid_from_ldap_raw(guid_raw)
                if dn_val and guid:
                    dn_to_guid[dn_val] = guid
        return [dn_to_guid[dn] for dn in group_dns if dn in dn_to_guid]

    def _build_server(self) -> Server:
        if self.mode == "ldaps":
            return Server(self.server_host, port=self.server_port, get_info=ALL, use_ssl=True, tls=self._tls)
        if self.mode == "starttls":
            return Server(self.server_host, port=self.server_port, get_info=ALL, use_ssl=False, tls=self._tls)
        return Server(self.server_host, port=self.server_port, get_info=ALL)

    def _bind(self, server: Server, user: str, password: str) -> Connection:
        conn = Connection(server, user=user, password=password, auto_bind=False)
        try:
            conn.open()
        except Exception as exc:
            raise ValueError(f"LDAP connection open failed: {exc}") from exc
        if conn.closed:
            raise ValueError("LDAP connection open failed: connection closed after open")
        if self.mode == "starttls":
            if not conn.start_tls():
                conn.unbind()
                raise ValueError("LDAP STARTTLS failed")
        if not conn.bind():
            conn.unbind()
            raise ValueError("LDAP bind failed")
        return conn

    def authenticate(self, username: str, password: str) -> LDAPUserInfo:
        if not username or not password:
            raise ValueError("Username and password are required")
        upn = username if "@" in username else f"{username}@{self.domain}"
        server = self._build_server()
        safe_upn = escape_filter_chars(upn)
        svc_conn = self._bind(server, user=self.bind_dn, password=self.bind_password)
        try:
            svc_conn.search(
                search_base=self.users_dn,
                search_filter=f"(userPrincipalName={safe_upn})",
                attributes=["distinguishedName", "memberOf", "sAMAccountName", "userPrincipalName"],
                size_limit=1,
            )
            if not svc_conn.entries:
                raise ValueError("User not found in LDAP")
            entry = svc_conn.entries[0]
            user_dn = str(entry.entry_dn)
            user_conn = self._bind(server, user=user_dn, password=password)
            user_conn.unbind()
            member_of: list[str] = []
            if "memberOf" in entry and entry.memberOf.values:
                member_of = [str(v) for v in entry.memberOf.values]
            group_guids = self._resolve_group_guids(svc_conn, member_of)
            short_name = username
            if "sAMAccountName" in entry and entry.sAMAccountName.value:
                short_name = str(entry.sAMAccountName.value)
            return LDAPUserInfo(username=short_name, user_dn=user_dn, groups=member_of, group_guids=group_guids)
        finally:
            svc_conn.unbind()

    def resolve_group_guids(self, group_dns: list[str]) -> list[str]:
        """Resolve group objectGUIDs for a list of group DNs using service bind."""
        if not group_dns:
            return []
        server = self._build_server()
        svc_conn = self._bind(server, user=self.bind_dn, password=self.bind_password)
        try:
            return self._resolve_group_guids(svc_conn, group_dns)
        finally:
            svc_conn.unbind()

    def search_groups(self, term: str, limit: int = 20) -> list[dict[str, str | None]]:
        q = (term or "").strip()
        if len(q) < 2:
            return []
        server = self._build_server()
        svc_conn = self._bind(server, user=self.bind_dn, password=self.bind_password)
        try:
            safe = escape_filter_chars(q)
            search_filter = f"(&(objectClass=group)(|(cn=*{safe}*)(description=*{safe}*)))"
            svc_conn.search(
                search_base=self._base_dn, search_filter=search_filter,
                search_scope=SUBTREE, attributes=["objectGUID", "distinguishedName", "cn", "description"],
                size_limit=max(1, min(limit, 200)),
            )
            out: list[dict[str, str | None]] = []
            for e in svc_conn.entries:
                guid_raw = e.objectGUID.value if "objectGUID" in e else None
                guid = self._guid_from_ldap_raw(guid_raw)
                if not guid:
                    continue
                dn = str(e.distinguishedName.value) if "distinguishedName" in e and e.distinguishedName.value else str(e.entry_dn)
                cn = str(e.cn.value) if "cn" in e and e.cn.value else dn
                desc = str(e.description.value) if "description" in e and e.description.value else None
                out.append({"guid": guid, "dn": dn, "cn": cn, "description": desc})
            return out
        finally:
            svc_conn.unbind()

    def list_groups(self, limit: int = 20000) -> list[dict[str, str | None]]:
        server = self._build_server()
        svc_conn = self._bind(server, user=self.bind_dn, password=self.bind_password)
        try:
            svc_conn.search(
                search_base=self._base_dn, search_filter="(objectClass=group)",
                search_scope=SUBTREE, attributes=["objectGUID", "distinguishedName", "cn", "description"],
                size_limit=max(1, min(limit, 50000)),
            )
            out: list[dict[str, str | None]] = []
            for e in svc_conn.entries:
                guid_raw = e.objectGUID.value if "objectGUID" in e else None
                guid = self._guid_from_ldap_raw(guid_raw)
                if not guid:
                    continue
                dn = str(e.distinguishedName.value) if "distinguishedName" in e and e.distinguishedName.value else str(e.entry_dn)
                cn = str(e.cn.value) if "cn" in e and e.cn.value else dn
                desc = str(e.description.value) if "description" in e and e.description.value else None
                out.append({"guid": guid, "dn": dn, "cn": cn, "description": desc})
            return out
        finally:
            svc_conn.unbind()

    def is_password_change_supported(self) -> bool:
        return self.mode in {"starttls", "ldaps"}

    def find_user_dn(self, username: str) -> str | None:
        upn = username if "@" in username else f"{username}@{self.domain}"
        safe_upn = escape_filter_chars(upn)
        server = self._build_server()
        svc_conn = self._bind(server, user=self.bind_dn, password=self.bind_password)
        try:
            svc_conn.search(
                search_base=self.users_dn,
                search_filter=f"(userPrincipalName={safe_upn})",
                attributes=["distinguishedName"], size_limit=1,
            )
            if not svc_conn.entries:
                return None
            return str(svc_conn.entries[0].entry_dn)
        finally:
            svc_conn.unbind()

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        if not self.is_password_change_supported():
            raise ValueError("Password change requires LDAP STARTTLS or LDAPS")
        user_dn = self.find_user_dn(username)
        if not user_dn:
            raise ValueError("User not found")
        server = self._build_server()
        conn = self._bind(server, user=user_dn, password=current_password)
        try:
            old_quoted = f'"{current_password}"'.encode("utf-16-le")
            new_quoted = f'"{new_password}"'.encode("utf-16-le")
            ok = conn.modify(
                user_dn,
                {"unicodePwd": [(MODIFY_DELETE, [old_quoted]), (MODIFY_ADD, [new_quoted])]},
            )
            if not ok:
                raise ValueError(f"Password change failed: {conn.result.get('description')}")
        finally:
            conn.unbind()
