#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import logging
import json
import ssl
import uuid
import version
from datetime import datetime
from enum import Enum
from zeroconf import ServiceBrowser, Zeroconf
import aiohttp

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

    def add_service(self, zeroconf, svc_type, name):
        info = zeroconf.get_service_info(svc_type, name)
        uuid = name.replace("." + svc_type, "")
        txt_records = {"uuid": uuid}
        for k in info.properties:
            txt_records[k.decode("utf-8")] = info.properties[k].decode("utf-8")

        self.terncy.discovered_homecenters[uuid] = txt_records
        print("\nservice state\n", self.terncy.discovered_homecenters)


class Terncy:
    def __init__(self, client_id, ip, port=443, username="", token=""):
        self.client_id = client_id
        self.ip = ip
        self.port = port
        self.username = username
        self.token = token
        self.token_id = -1
        self.token_state = TokenState.INVALID
        self.discovered_homecenters = {}
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

    async def discover(self):
        zc = Zeroconf()
        listener = TerncyZCListener(self)
        browser = ServiceBrowser(zc, "_websocket._tcp.local.", listener)
        browser.run()
        await asyncio.sleep(15)
        browser.cancel()
        zc.close()
        return self.discovered_homecenters

    async def start(self):
        """Connect to Terncy system and start event monitor."""
        logger.info(
            "Terncy v%s starting connection to %s:%d.",
            version.__version__,
            self.ip,
            self.port,
        )
        asyncio.ensure_future(self._send_routine())
        return await self._start_websocket()

    async def _send_routine(self):
        while True:
            await asyncio.sleep(5)
            # await self.get_entities("device", True)

    async def _start_websocket(self):
        url = "wss://%s:%d/ws/json?clientId=%s&username=%s&token=%s" % (
            self.ip,
            self.port,
            self.client_id,
            self.username,
            self.token,
        )
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url, ssl=ssl._create_unverified_context()
            ) as ws:
                self._connection = ws
                async for msg in ws:
                    msgObj = msg.json()
                    print("got message:", datetime.now())
                    print(msgObj)
                    if "rspId" in msgObj:
                        rsp_id = msgObj["rspId"]

                        if rsp_id in self._pending_requests:
                            req = self._pending_requests[rsp_id]
                            req["_response"] = msgObj
                            req["event"].set()
                    if "intent" in msgObj and msgObj["intent"] == "event":
                        if self._event_handler:
                            self._event_handler(self, msgObj)

    async def _wait_for_response(self, req_id, req, timeout):
        evt = asyncio.Event()
        request = {
            "req": req,
            "time": datetime.now(),
            "event": evt,
        }

        self._pending_requests[req_id] = request
        aw = asyncio.ensure_future(evt.wait())
        done, pending = await asyncio.wait({aw}, timeout=timeout)
        if aw in done:
            print("wait response ok", datetime.now())
        else:
            print("wait response timeout", datetime.now())
        if req_id in self._pending_requests:
            self._pending_requests.pop(req_id)

    async def get_entities(self, ent_type, wait_result=False, timeout=5):
        req_id = _next_req_id()
        data = {
            "reqId": req_id,
            "intent": "sync",
            "type": ent_type,
        }
        await self._connection.send_str(json.dumps(data))
        if wait_result:
            await self._wait_for_response(req_id, data, timeout)

    async def set_onoff(self, ent_uuid, state, wait_result=False, timeout=5):
        return self.set_attribute(ent_uuid, "on", state, 0, wait_result)

    async def set_attribute(
        self, ent_uuid, attr, attr_val, method, wait_result=False, timeout=5
    ):
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
        await self._connection.send_str(json.dumps(data))
        if wait_result:
            await self._wait_for_response(req_id, data, timeout)
