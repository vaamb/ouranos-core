from fastapi import HTTPException, status


def empty_result(result):
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="No content found"
    )


def assert_single_uid(uid: str, name: str = "uid"):
    if len(uid.split(",")) > 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"`{name}` should be a single valid {name}"
        )
