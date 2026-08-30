"""Minimal Agora AccessToken2 (Token007) implementation for RTC tokens."""

import base64
import hmac
import random
import struct
import time
import zlib
from collections import OrderedDict
from hashlib import sha256


def pack_uint16(value):
    return struct.pack("<H", value)


def pack_uint32(value):
    return struct.pack("<I", value)


def pack_int16(value):
    return struct.pack("<h", value)


def pack_string(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return pack_uint16(len(value)) + value


def pack_map_uint32(values):
    result = pack_uint16(len(values))
    for key in sorted(values.keys()):
        result += pack_uint16(key) + pack_uint32(values[key])
    return result


class Service:
    def __init__(self, service_type):
        self._type = service_type
        self._privileges = {}

    def add_privilege(self, privilege, expire):
        self._privileges[privilege] = expire

    def service_type(self):
        return self._type

    def pack(self):
        privileges = OrderedDict(sorted(self._privileges.items(), key=lambda x: int(x[0])))
        return pack_uint16(self._type) + pack_map_uint32(privileges)


class ServiceRtc(Service):
    kServiceType = 1
    kPrivilegeJoinChannel = 1
    kPrivilegePublishAudioStream = 2
    kPrivilegePublishVideoStream = 3
    kPrivilegePublishDataStream = 4

    def __init__(self, channel_name="", uid=0):
        super().__init__(ServiceRtc.kServiceType)
        self._channel_name = channel_name.encode("utf-8")
        self._uid = b"" if uid == 0 else str(uid).encode("utf-8")

    def pack(self):
        return super().pack() + pack_string(self._channel_name) + pack_string(self._uid)


class AccessToken:
    def __init__(self, app_id="", app_certificate="", issue_ts=0, expire=900):
        random.seed(time.time())
        self._app_id = app_id
        self._app_cert = app_certificate
        self._issue_ts = issue_ts if issue_ts != 0 else int(time.time())
        self._expire = expire
        self._salt = random.randint(1, 99999999)
        self.services = []

    def _signing(self, app_certificate):
        signing = hmac.new(pack_uint32(self._issue_ts), app_certificate, sha256).digest()
        return hmac.new(pack_uint32(self._salt), signing, sha256).digest()

    def _build_check(self):
        def is_hex_uuid(data):
            if len(data) != 32:
                return False
            try:
                bytearray.fromhex(data)
            except (TypeError, ValueError):
                return False
            return True

        return bool(self.services) and is_hex_uuid(self._app_id) and is_hex_uuid(self._app_cert)

    def add_service(self, service):
        self.services.append(service)

    def build(self):
        if not self._build_check():
            return ""
        app_id = self._app_id.encode("utf-8")
        app_cert = self._app_cert.encode("utf-8")
        signing = self._signing(app_cert)
        services = sorted(self.services, key=lambda s: s.service_type())
        signing_info = (
            pack_string(app_id)
            + pack_uint32(self._issue_ts)
            + pack_uint32(self._expire)
            + pack_uint32(self._salt)
            + pack_uint16(len(services))
        )
        for service in services:
            signing_info += service.pack()
        signature = hmac.new(signing, signing_info, sha256).digest()
        return "007" + base64.b64encode(zlib.compress(pack_string(signature) + signing_info)).decode("utf-8")


Role_Publisher = 1


def build_token_with_user_account(app_id, app_certificate, channel_name, account,
                                  role, token_expire, privilege_expire=0):
    """Build an RTC token bound to a string user account."""
    token = AccessToken(app_id, app_certificate, expire=token_expire)
    rtc_service = ServiceRtc(channel_name, account)
    rtc_service.add_privilege(ServiceRtc.kPrivilegeJoinChannel, privilege_expire)
    if role == Role_Publisher:
        rtc_service.add_privilege(ServiceRtc.kPrivilegePublishAudioStream, privilege_expire)
        rtc_service.add_privilege(ServiceRtc.kPrivilegePublishVideoStream, privilege_expire)
        rtc_service.add_privilege(ServiceRtc.kPrivilegePublishDataStream, privilege_expire)
    token.add_service(rtc_service)
    return token.build()
