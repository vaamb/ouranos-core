from fastapi import HTTPException, status


def assert_single_uid(uid: str, name: str = "uid"):
    if len(uid.split(",")) > 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"`{name}` should be a single valid {name}"
        )
