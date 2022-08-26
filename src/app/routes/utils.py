from fastapi import FastAPI, HTTPException, status


def empty_result(result):
    raise HTTPException(
        status_code=status.HTTP_204_NO_CONTENT,
        detail="Empty result",
    )
