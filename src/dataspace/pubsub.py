from queue import Queue


class Broker:
    def __init__(self) -> None:
        self.clients = set()

    def link(self, client) -> None:
        self.clients.add(client)

    def push(self, payload: dict) -> int:
        pushed = 0
        for client in self.clients:
            if payload["channel"] in client.channels:
                client.messages.put(payload)
                pushed += 1
        return pushed


_broker = Broker()


class StupidPubSub:
    def __init__(self, broker: Broker = None) -> None:
        if not broker:
            self.broker = _broker
        else:
            if isinstance(broker, Broker):
                self.broker = broker
            else:
                raise TypeError("broker needs to be an instance of Broker()")
        self.broker.link(self)
        self.channels = set()
        self.messages = Queue()

    def subscribe(self, channel: str) -> None:
        self.channels.add(channel)

    def unsubscribe(self, channel: str = None) -> None:
        if channel:
            self.channels.remove(channel)
        else:
            self.channels.clear()

    def publish(self, channel: str, message: dict) -> int:
        payload = {"channel": channel, "data": message}
        published = self.broker.push(payload)
        return published

    def get_message(self) -> dict:
        if self.messages.qsize():
            return self.messages.get(timeout=0.01)
        return {}

    def listen(self):
        while self.subscribed:
            response = self.messages.get()
            if response is not None:
                yield response

    @property
    def subscribed(self) -> bool:
        return bool(self.channels)
