from queue import Queue


class Broker:
    def __init__(self):
        self.clients = set()

    def link(self, client):
        self.clients.add(client)

    def push(self, payload):
        pushed = 0
        for client in self.clients:
            if payload["channel"] in client.channels:
                client.messages.put(payload)
                pushed += 1
        return pushed


_broker = Broker()


class StupidPubSub:
    def __init__(self, broker=None):
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

    def subscribe(self, channel):
        self.channels.add(channel)

    def unsubscribe(self, channel):
        self.channels.remove(channel)

    def publish(self, channel, message):
        payload = {"channel": channel, "data": message}
        published = self.broker.push(payload)
        return published

    def get_message(self):
        if self.messages.qsize():
            return self.messages.get()
        return {}
