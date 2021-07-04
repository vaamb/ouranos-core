import logging
from threading import Event, Thread
import time

from utils import jsonWrapper as json


logger = logging.getLogger("dispatcher")


class BaseDispatcher:
    def __init__(self, name):
        self.name = name
        self.handlers = {}
        self._fallback = None
        self.threads = {}
        self._subscribe(f"to_{name}")
        self._running = Event()

    def _subscribe(self, channel):
        raise NotImplementedError(
            "This method needs to be implemented in a subclass"
        )

    def _publish(self, channel: str, payload: dict):
        raise NotImplementedError(
            "This method needs to be implemented in a subclass"
        )

    def on(self, event: str, handler=None):
        def set_handler(handler):
            self.handlers[event] = handler
            return handler

        if handler is None:
            return set_handler
        set_handler(handler)

    @property
    def fallback(self):
        return self._fallback

    @fallback.setter
    def fallback(self, fct):
        self._fallback = fct

    def emit(self, namespace: str, event: str, *args, **kwargs):
        payload = {"event": event}
        if args:
            payload.update({"args": args})
        if kwargs:
            payload.update({"kwargs": kwargs})
        self._publish(f"to_{namespace}", payload)

    def main_loop(self):
        while self._running.is_set():
            message = self._parse_payload(self._get_message())
            if message:
                event = message["event"]
                args = message.get("args", ())
                kwargs = message.get("kwargs", {})
                self._trigger_event(event, *args, **kwargs)
            time.sleep(0.01)

    def _get_message(self) -> dict:
        raise NotImplementedError(
            "This method needs to be implemented in a subclass"
        )

    def _parse_payload(self, payload: dict) -> dict:
        raise NotImplementedError(
            "This method needs to be implemented in a subclass"
        )

    def _trigger_event(self, event: str, *args, **kwargs):
        if event in self.handlers:
            try:
                return self.handlers[event](*args, **kwargs)
            except Exception as e:
                logger.error(e)
                return
        else:
            if self._fallback:
                try:
                    return self._fallback(*args, **kwargs)
                except Exception as e:
                    logger.error(e)
                    return

    def start_background_task(self, target, *args):
        """Override to use another threading method"""
        t = Thread(target=target, args=args)
        t.start()
        self.threads[target.__name__] = target

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        self.start_background_task(target=self.main_loop)

    def stop(self):
        self._running.clear()
        for thread in self.threads:
            thread.join()


class PubSubDispatcher(BaseDispatcher):
    def __init__(self, name, pubsub):
        self.pubsub = pubsub
        super(PubSubDispatcher, self).__init__(name)
    
    def _subscribe(self, channel):
        self.pubsub.subscribe(channel)
    
    def _publish(self, channel, payload):
        return self.pubsub.publish(channel, payload)
    
    def _get_message(self):
        return self.pubsub.get_message()
    
    def _parse_payload(self, payload):
        message = payload.get("data", {})
        return message


class RedisDispatcher(BaseDispatcher):
    def __init__(self, name, redis_client):
        self.redis = redis_client
        self.pubsub = redis_client.pubsub()
        super(RedisDispatcher, self).__init__(name)

    def _subscribe(self, channel):
        self.pubsub.subscribe(channel)

    def _publish(self, channel, payload):
        message = json.dumps(payload)
        return self.redis.publish(channel, message)

    def _get_message(self):
        return self.pubsub.get_message(ignore_subscribe_messages=True) or {}

    def _parse_payload(self, payload):
        if payload:
            message = payload["data"].decode("utf-8")
            message = json.loads(message)
            return message
        return {}
