from __future__ import annotations

import enum
from typing import cast, Literal, TypedDict


from dispatcher import (
    AsyncDispatcher,
    AsyncInMemoryDispatcher,
    AsyncRedisDispatcher,
    AsyncAMQPDispatcher
)


class DispatcherType(enum.Enum):
    memory = enum.auto()
    amqp = enum.auto()
    redis = enum.auto()


DispatcherName = Literal["aggregator", "aggregator-stream", "application"]


class DispatcherOptions:
    __options: dict[DispatcherName, dict[str | enum.Enum, str | dict]] = {
        "aggregator": {
            "uri_cfg_lookup": "GAIA_COMMUNICATION_URL",
            DispatcherType.memory: {},
            DispatcherType.amqp: {
                "queue_options": {
                    "arguments": {
                        # Remove queue after 1 day without consumer
                        "x-expires": 24 * 60 * 60 * 1000,
                        # Keep messages for 12 hours then remove them
                        "x-message-ttl": 12 * 12 * 60 * 1000,
                    },
                },
            },
            DispatcherType.redis: {},
        },
        "aggregator-stream": {
            "uri_cfg_lookup": "GAIA_COMMUNICATION_URL",
            DispatcherType.memory: {},
            DispatcherType.amqp: {
                "queue_options": {
                    "arguments": {
                        # Remove queue after 15 min without consumer
                        "x-expires": 15 * 60 * 1000,
                        # Keep messages only 15 sec then remove them
                        "x-message-ttl": 15 * 1000,
                    },
                },
            },
            DispatcherType.redis: {},
        },
        "application": {
            "uri_cfg_lookup": "DISPATCHER_URL",
            DispatcherType.memory: {},
            DispatcherType.amqp: {
                "queue_options": {
                    "arguments": {
                        # Remove queue after 1 day without consumer
                        "x-expires": 24 * 60 * 60 * 1000,
                        # Keep messages only 1 minute then remove them
                        "x-message-ttl": 1 * 60 * 1000,
                    },
                },
            },
            DispatcherType.redis: {},
        },
    }

    @classmethod
    def set_options(
            cls,
            dispatcher_name: DispatcherName,
            dispatcher_type: DispatcherType,
            options: dict
    ) -> None:
        cls.__options[dispatcher_name][dispatcher_type] = options

    @classmethod
    def get_uri_lookup(cls, dispatcher_name: DispatcherName) -> str:
        return cls.__options[dispatcher_name]["uri_cfg_lookup"]

    @classmethod
    def get_option(
            cls,
            dispatcher_name: DispatcherName,
            dispatcher_type: DispatcherType,
    ) -> dict:
        return cls.__options[dispatcher_name][dispatcher_type]


class DispatcherFactory:
    __dispatchers: dict[str, AsyncDispatcher] = {}

    @classmethod
    def get(
            cls,
            name: str,
            broker_uri: str | None = None,
            broker_options: dict | None = None,
            config: dict | None = None,
    ) -> AsyncDispatcher:
        try:
            return cls.__dispatchers[name]
        except KeyError:
            if config is None:
                from ouranos import current_app
                config = current_app.config
            if broker_uri is None:
                name = cast(DispatcherName, name)
                uri_cfg_lookup = DispatcherOptions.get_uri_lookup(name)
                broker_uri = config[uri_cfg_lookup]

            if broker_uri.startswith("memory://"):
                broker_options = broker_options or DispatcherOptions.get_option(
                    name, DispatcherType.memory)
                dispatcher = AsyncInMemoryDispatcher(name, **broker_options)
            elif broker_uri.startswith("amqp://"):
                if broker_uri == "amqp://":
                    # Use default rabbitmq uri
                    broker_uri = "amqp://guest:guest@localhost:5672//"
                broker_options = broker_options or DispatcherOptions.get_option(
                    name, DispatcherType.amqp)
                dispatcher = AsyncAMQPDispatcher(name, url=broker_uri, **broker_options)
            elif broker_uri.startswith("redis://"):
                if broker_uri == "redis://":
                    # Use default Redis uri
                    broker_uri = "redis://localhost:6379/0"
                broker_options = broker_options or DispatcherOptions.get_option(
                    name, DispatcherType.redis)
                dispatcher = AsyncRedisDispatcher(name, url=broker_uri, **broker_options)
            else:
                raise RuntimeError(
                    "'broker_uri' is not set to a supported protocol, choose"
                    "from 'memory://', 'redis://' or 'amqp://'"
                )

            cls.__dispatchers[name] = dispatcher
            return cls.__dispatchers[name]
