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

logger = logging.getLogger("terncy.log")


def _next_req_id():
    return uuid.uuid4().hex[0:8]


class TokenState(Enum):
    INVALID = -1
    REQUESTED = 1
    APPROVED = 3


class TerncyZCListener(object):
    def __init__(self, terncy):
        self.terncy = terncy

    def remove_service(self, zeroconf, svc_type, name):
        uuid = name.replace("." + svc_type, "")
        if uuid in self.terncy.discovered_homecenters:
            self.terncy.discovered_homecenters.pop(uuid)

    def update_service(self, zeroconf, svc_type, name):
        info = zeroconf.get_service_info(svc_type, name)
        uuid = name.replace("." + svc_type, "")
        txt_records = {"uuid": uuid}
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

        self.terncy.discovered_homecenters[uuid] = txt_records
        print("\nservice state\n", self.terncy.discovered_homecenters)

    def add_service(self, zeroconf, svc_type, name):
        info = zeroconf.get_service_info(svc_type, name)
        uuid = name.replace("." + svc_type, "")
        txt_records = {"uuid": uuid}
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

        self.terncy.discovered_homecenters[uuid] = txt_records
        print("\nservice state\n", self.terncy.discovered_homecenters)


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
        self.discovered_homecenters = {}
        self._discovery_engine = None
        self._discovery_browser = None
        self._discovery_listener = None
        self._connection = None
        self._pending_requests = {}
        self._event_handler = None

    def register_event_handler(self, handler):
        self._event_handler = handler

    async def request_token(self, username, name):
        url = "https://%s:%d/v1/tokens:request" % (self.ip, self.port)
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
                print("status:", response.status)
                print("headers", response.headers)
                body = await response.json()
                print("body:", body)
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
        url = "https://%s:%d/v1/tokens:request" % (self.ip, self.port)
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
                print("status:", response.status)
                print("headers", response.headers)
                return response.status

    async def check_token_state(self, token_id, token=""):
        url = "https://%s:%d/v1/tokens:query" % (self.ip, self.port)
        async with aiohttp.ClientSession() as session:
            data = {
                "reqId": _next_req_id(),
                "intent": "queryToken",
                "clientId": self.client_id,
                "token": token,
                "id": token_id,
            }
            print("req", json.dumps(data))
            async with session.post(
                url,
                data=json.dumps(data),
                ssl=ssl._create_unverified_context(),
            ) as response:
                print("status:", response.status)
                print("headers", response.headers)
                body = await response.json()
                print("body:", body)
                state = TokenState.INVALID
                if "state" in body:
                    state = body["state"]
                return response.status, state

    async def start_discovery(self, listener):
        if self._discovery_engine is None:
            zc = Zeroconf()
            browser = ServiceBrowser(zc, "_websocket._tcp.local.", listener)
            self._discovery_engine = zc
            self._discovery_browser = browser
            self._discovery_listener = listener

    async def stop_discovery(self, listener):
        if self._discovery_engine is not None:
            self._discovery_engine.close()
            self._discovery_browser.cancel()
            self._discovery_engine = None
            self._discovery_browser = None
            self._discovery_listener = None

    async def discover(self):
        zc = Zeroconf()
        listener = TerncyZCListener(self)
        browser = ServiceBrowser(zc, "_websocket._tcp.local.", listener)
        browser.run()
        await asyncio.sleep(3)
        browser.cancel()
        zc.close()
        return self.discovered_homecenters

    async def start(self):
        """Connect to Terncy system and start event monitor."""
        print(
            "Terncy v%s starting connection to %s:%d.",
            __version__,
            self.ip,
            self.port,
        )
        return await self._start_websocket()

    async def stop(self):
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _start_websocket(self):
        url = "wss://%s:%d/ws/json?clientId=%s&username=%s&token=%s" % (
            self.ip,
            self.port,
            self.client_id,
            self.username,
            self.token,
        )
        try:
            ssl_no_verify = ssl._create_unverified_context()
            async with websockets.connect(
                url, ping_timeout=None, ping_interval=None, ssl=ssl_no_verify
            ) as ws:
                self._connection = ws
                if self._event_handler:
                    self._event_handler(self, event.Connected())
                    print("connected to server:", datetime.now())
                async for msg in ws:
                    msgObj = json.loads(msg)
                    print(msgObj)
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
            print("failed to connect server:", datetime.now())
            print(e)
            if self._event_handler:
                self._event_handler(self, event.Disconnected())
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
            print("wait response timeout", datetime.now())
        if req_id in self._pending_requests:
            self._pending_requests.pop(req_id)
        return response_desc

    async def get_entities(self, ent_type, wait_result=False, timeout=5):
        if self._connection is None:
            print("can't send without connection")
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

    async def set_onoff(self, ent_uuid, state, wait_result=False, timeout=5):
        if self._connection is None:
            print("can't send without connection")
            return None
        return await self.set_attribute(ent_uuid, "on", state, 0, wait_result)

    async def set_attribute(
        self, ent_uuid, attr, attr_val, method, wait_result=False, timeout=5
    ):
        if self._connection is None:
            print("can't send without connection")
            return None
        req_id = _next_req_id()
        data = {
            "reqId": req_id,
            "intent": "execute",
            "entities": [
                {
                    "id": ent_uuid,
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
        await self._connection.send(json.dumps(data))
        if wait_result:
            return await self._wait_for_response(req_id, data, timeout)
