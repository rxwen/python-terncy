#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import logging
import json
import ssl
import uuid
from terncy.version import __version__
import terncy.event as event
import ipaddress
from datetime import datetime
from enum import Enum
from zeroconf import ServiceBrowser, Zeroconf
import aiohttp
import websockets

_LOGGER = logging.getLogger(__name__)


def _next_req_id():
    return uuid.uuid4().hex[0:8]


class TokenState(Enum):
    INVALID = -1
    REQUESTED = 1
    APPROVED = 3


TERNCY_HUB_SVC_NAME = "_websocket._tcp.local."

WAIT_RESP_TIMEOUT_SEC = 5

_discovery_engine = None
_discovery_browser = None

discovered_homecenters = {}


class _TerncyZCListener:
    def __init__(self):
        pass

    def remove_service(self, zeroconf, svc_type, name):
        global discovered_homecenters
        dev_id = name.replace("." + svc_type, "")
        if dev_id in discovered_homecenters:
            discovered_homecenters.pop(dev_id)

    def update_service(self, zeroconf, svc_type, name):
        global discovered_homecenters
        info = zeroconf.get_service_info(svc_type, name)
        dev_id = name.replace("." + svc_type, "")
        txt_records = {"dev_id": dev_id}
        ip = ""
        if len(info.addresses) > 0:
            if len(info.addresses[0]) == 4:
                ip = str(ipaddress.IPv4Address(info.addresses[0]))
            if len(info.addresses[0]) == 16:
                ip = str(ipaddress.IPv6Address(info.addresses[0]))
        txt_records["ip"] = ip
        txt_records["port"] = info.port
        for k in info.properties:
            txt_records[k.decode("utf-8")] = info.properties[k].decode("utf-8")

        discovered_homecenters[dev_id] = txt_records

    def add_service(self, zeroconf, svc_type, name):
        global discovered_homecenters
        info = zeroconf.get_service_info(svc_type, name)
        dev_id = name.replace("." + svc_type, "")
        txt_records = {"dev_id": dev_id}
        ip = ""
        if len(info.addresses) > 0:
            if len(info.addresses[0]) == 4:
                ip = str(ipaddress.IPv4Address(info.addresses[0]))
            if len(info.addresses[0]) == 16:
                ip = str(ipaddress.IPv6Address(info.addresses[0]))
        txt_records["ip"] = ip
        txt_records["port"] = info.port
        for k in info.properties:
            txt_records[k.decode("utf-8")] = info.properties[k].decode("utf-8")

        discovered_homecenters[dev_id] = txt_records


async def start_discovery():
    global _discovery_engine
    global _discovery_browser
    if _discovery_engine is None:
        zc = Zeroconf()
        listener = _TerncyZCListener()
        browser = ServiceBrowser(zc, TERNCY_HUB_SVC_NAME, listener)
        _discovery_engine = zc
        _discovery_browser = browser


async def stop_discovery():
    global _discovery_engine
    global _discovery_browser
    if _discovery_engine is not None:
        _discovery_browser.cancel()
        _discovery_engine.close()
        _discovery_engine = None
        _discovery_browser = None


class Terncy:
    def __init__(self, client_id, dev_id, ip, port=443, username="", token=""):
        self.client_id = client_id
        self.dev_id = dev_id
        self.ip = ip
        self.port = port
        self.username = username
        self.token = token
        self.token_id = -1
        self.token_state = TokenState.INVALID
        self._connection = None
        self._pending_requests = {}
        self._event_handler = None

    def is_connected(self):
        return self._connection is not None

    def register_event_handler(self, handler):
        self._event_handler = handler

    async def request_token(self, username, name):
        url = f"https://{self.ip}:{self.port}/v1/tokens:request"
        async with aiohttp.ClientSession() as session:
            data = {
                "reqId": _next_req_id(),
                "intent": "requestToken",
                "clientId": self.client_id,
                "username": self.username,
                "name": name,
                "role": 3,
            }
            async with session.post(
                url,
                data=json.dumps(data),
                ssl=ssl._create_unverified_context(),
            ) as response:
                body = await response.json()
                _LOGGER.debug(f"resp body: {body}")
                state = TokenState.INVALID
                token = ""
                token_id = -1
                if "state" in body:
                    state = body["state"]
                if "id" in body:
                    token_id = body["id"]
                if "token" in body:
                    token = body["token"]
                return response.status, token_id, token, state

    async def delete_token(self, token_id, token):
        url = f"https://{self.ip}:{self.port}/v1/tokens:delete"
        async with aiohttp.ClientSession() as session:
            data = {
                "reqId": _next_req_id(),
                "intent": "deleteToken",
                "clientId": self.client_id,
                "id": token_id,
                "token": token,
            }
            async with session.post(
                url,
                data=json.dumps(data),
                ssl=ssl._create_unverified_context(),
            ) as response:
                _LOGGER.debug(f"resp: {response}")
                return response.status

    async def check_token_state(self, token_id, token=""):
        url = f"https://{self.ip}:{self.port}/v1/tokens:query"
        async with aiohttp.ClientSession() as session:
            data = {
                "reqId": _next_req_id(),
                "intent": "queryToken",
                "clientId": self.client_id,
                "token": token,
                "id": token_id,
            }
            async with session.post(
                url,
                data=json.dumps(data),
                ssl=ssl._create_unverified_context(),
            ) as response:
                body = await response.json()
                _LOGGER.debug(f"resp: {response}")
                state = TokenState.INVALID
                if "state" in body:
                    state = body["state"]
                return response.status, state

    async def start(self):
        """Connect to Terncy system and start event monitor."""
        _LOGGER.info(f"Terncy v{__version__} starting connection to:")
        _LOGGER.info(f"{self.dev_id} {self.ip}:{self.port}")
        return await self._start_websocket()

    async def stop(self):
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _start_websocket(self):
        url = f"wss://{self.ip}:{self.port}/ws/json?clientId={self.client_id}&username={self.username}&token={self.token}"
        try:
            ssl_no_verify = ssl._create_unverified_context()
            async with websockets.connect(
                url, ping_timeout=None, ping_interval=None, ssl=ssl_no_verify
            ) as ws:
                self._connection = ws
                if self._event_handler:
                    _LOGGER.info(f"connected to {self.dev_id}")
                    self._event_handler(self, event.Connected())
                async for msg in ws:
                    msgObj = json.loads(msg)
                    _LOGGER.debug(f"recv {self.dev_id} msg: {msgObj}")
                    if "rspId" in msgObj:
                        rsp_id = msgObj["rspId"]

                        if rsp_id in self._pending_requests:
                            req = self._pending_requests[rsp_id]
                            req["rsp"] = msgObj
                            req["event"].set()
                    if "intent" in msgObj and msgObj["intent"] == "event":
                        if self._event_handler:
                            ev = event.EventMessage(msgObj)
                            self._event_handler(self, ev)
                    if "intent" in msgObj and msgObj["intent"] == "ping":
                        await ws.send('{"intent":"pong"}')
        except (
            aiohttp.client_exceptions.ClientConnectionError,
            websockets.exceptions.ConnectionClosedError,
            ConnectionRefusedError,
            OSError,
            websockets.exceptions.InvalidStatusCode,
        ) as e:
            _LOGGER.info(f"disconnect with {self.dev_id} {e}")
            if self._event_handler:
                self._event_handler(self, event.Disconnected())
            self._connection = None
            return

    async def _wait_for_response(self, req_id, req, timeout):
        """ return the request and its response """
        evt = asyncio.Event()
        response_desc = {
            "req": req,
            "time": datetime.now(),
            "event": evt,
        }

        self._pending_requests[req_id] = response_desc
        aw = asyncio.ensure_future(evt.wait())
        done, pending = await asyncio.wait({aw}, timeout=timeout)
        if aw in done:
            pass
        else:
            _LOGGER.info(f"wait {self.dev_id} response timeout")
        if req_id in self._pending_requests:
            self._pending_requests.pop(req_id)
        return response_desc

    async def get_entities(
        self, ent_type, wait_result=False, timeout=WAIT_RESP_TIMEOUT_SEC
    ):
        if self._connection is None:
            _LOGGER.info(f"no connection with {self.dev_id}")
            return None
        req_id = _next_req_id()
        data = {
            "reqId": req_id,
            "intent": "sync",
            "type": ent_type,
        }
        await self._connection.send(json.dumps(data))
        if wait_result:
            return await self._wait_for_response(req_id, data, timeout)

    async def set_onoff(
        self, ent_id, state, wait_result=False, timeout=WAIT_RESP_TIMEOUT_SEC
    ):
        if self._connection is None:
            _LOGGER.info(f"no connection with {self.dev_id}")
            return None
        return await self.set_attribute(ent_id, "on", state, 0, wait_result)

    async def set_attribute(
        self,
        ent_id,
        attr,
        attr_val,
        method,
        wait_result=False,
        timeout=WAIT_RESP_TIMEOUT_SEC,
    ):
        if self._connection is None:
            _LOGGER.info(f"no connection with {self.dev_id}")
            return None
        req_id = _next_req_id()
        data = {
            "reqId": req_id,
            "intent": "execute",
            "entities": [
                {
                    "id": ent_id,
                    "attributes": [
                        {
                            "attr": attr,
                            "value": attr_val,
                            "method": method,
                        }
                    ],
                }
            ],
        }
        try:
            await self._connection.send(json.dumps(data))
        except (
            aiohttp.client_exceptions.ClientConnectionError,
            websockets.exceptions.ConnectionClosedError,
            ConnectionRefusedError,
            OSError,
            websockets.exceptions.InvalidStatusCode,
        ) as e:
            _LOGGER.info(f"send failed {self.dev_id} {e}")
            if self._event_handler:
                self._event_handler(self, event.Disconnected())
            self._connection = None
            return None  # or raise again?
        if wait_result:
            return await self._wait_for_response(req_id, data, timeout)

    async def set_attributes(
        self,
        ent_id,
        attrs: list[dict],
        method,
        wait_result=False,
        timeout=WAIT_RESP_TIMEOUT_SEC,
    ):
        print(attrs)
        if self._connection is None:
            _LOGGER.info(f"no connection with {self.dev_id}")
            return None
        req_id = _next_req_id()
        data = {
            "reqId": req_id,
            "intent": "execute",
            "entities": [
                {
                    "id": ent_id,
                    "attributes": [
                        {
                            "attr": av["attr"],
                            "value": av["value"],
                            "method": method,
                        }
                        for av in attrs
                    ],
                }
            ],
        }
        try:
            await self._connection.send(json.dumps(data))
        except (
            aiohttp.client_exceptions.ClientConnectionError,
            websockets.exceptions.ConnectionClosedError,
            ConnectionRefusedError,
            OSError,
            websockets.exceptions.InvalidStatusCode,
        ) as e:
            _LOGGER.info(f"send failed {self.dev_id} {e}")
            if self._event_handler:
                self._event_handler(self, event.Disconnected())
            self._connection = None
            return None  # or raise again?
        if wait_result:
            return await self._wait_for_response(req_id, data, timeout)
