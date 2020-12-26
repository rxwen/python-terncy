#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import terncy


def event_hander(t, msg):
    print("got event", msg)


async def main():
    await terncy.start_discovery()
    await asyncio.sleep(2)
    await terncy.start_discovery()
    print(terncy.discovered_homecenters)

    # construct a Terncy object from discovered info
    t = terncy.Terncy(
        "client_id",
        "box-12-34-56-78-90-ab",
        "192.168.1.187",
        443,
        "homeassistant_user",
        "",
    )
    token_id, token = await t.request_token("homeassistant_user", "HA User")

    # approve the token request in Terncy app, the client should store the
    # allocated token and token id for later usage

    # create a new Terncy object with approved token
    t.token = token
    t.token_id = token_id
    t.register_event_handler(event_hander)
    await t.start()
    t.set_onoff("devid_of_device", 1)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
