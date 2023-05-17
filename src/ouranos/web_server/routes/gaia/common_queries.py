from fastapi import Query


ecosystems_uid_q = Query(
    default=None,
    description="A list of ecosystem ids (either uids or names), or 'recent' "
                "or 'connected'"
)
hardware_level_q = Query(
    default=None,
    description="The sensor_level at which the sensor gathers data. Leave empty for both"
)
