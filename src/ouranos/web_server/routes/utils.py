from fastapi import HTTPException, status


def empty_result(result):
    return result


def assert_single_uid(uid: str, name: str = "uid"):
    if "all" in uid or len(uid.split(",")) > 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"`{name}` should be a single valid {name}"
        )
