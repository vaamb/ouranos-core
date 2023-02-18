from fastapi import Query


ecosystems_uid_q = Query(
    default=None,
    description="A list of ecosystem ids (either uids or names), or 'recent' "
                "or 'connected'"
)
sensor_level_q = Query(
    default=None,
    description="The sensor_level at which the sensor gathers data. Choose from "
                "'plants', 'environment' or empty for both"
)
