import json
from queue import Queue

from dataspace.custom_dumps import dumps_dt


def _encode_value(value):
    if isinstance(value, bytes):
        raise TypeError("redisDict cannot store bytes object")
    return json.dumps(value, default=dumps_dt)


class redisQueue(Queue):
    def __init__(self, name, redis_client, check_client=True, *args, **kwargs):
        if check_client:
            if not redis_client.ping():
                raise RuntimeError(
                    f"Redis server could not be contacted, unable to "
                    f"instantiate {self.__class__.__name__}"
                )
        self._name = name
        self._redis_client = redis_client
        super(redisQueue, self).__init__(*args, **kwargs)

    def _init(self, maxsize):
        pass

    def _qsize(self):
        return self._redis_client.llen(self._name)

    def _put(self, item):
        self._redis_client.rpush(self._name,
                                 json.dumps(item, default=dumps_dt))

    # Get an item from the queue
    def _get(self):
        data = self._redis_client.lpop(self._name)
        try:
            return json.loads(data)
        except TypeError:
            return data
