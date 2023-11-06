# python-terncy
A python library for control ***[Terncy](https://www.terncy.com/)*** devices.

[![PyPI version](https://badge.fury.io/py/terncy.svg)](https://badge.fury.io/py/terncy) [![Build Status](https://travis-ci.org/rxwen/python-terncy.svg?branch=master)](https://travis-ci.org/rxwen/python-terncy)

## Installation

    pip install terncy

## Introduction

Before use this library, developer need to get a client id from terncy. The client id is a string that uniquely identifies the client app connectes to Terncy system. For istance, Home Assistant integration has its own client id. By presenting a valid client id to Terncy, it's allowed to access the system.

In addition, an access credential is also needed to make sure the owner of the Terncy system is aware of, and permit the client access. The approval of the access credential is done in Terncy app by the owner.


Example:

```
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

    attributes = [{"attr":"on", "value":1}, {"attr":"brightness", "value":42}]
    t.set_attributes("devid_of_device", attributes) 


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

```
