from __future__ import annotations

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Query, Path, Response, status,
    UploadFile)
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config.consts import MAX_PICTURE_FILE_SIZE, MAX_TEXT_FILE_SIZE
from ouranos.core.database.models.app import (
    WikiArticleNotFound, UserMixin, WikiArticle, WikiArticleModification,
    WikiArticlePicture, WikiTopic)
from ouranos.web_server.auth import get_current_user, is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.wiki import (
    WikiArticleInfo, WikiArticleModificationInfo, WikiArticleCreationPayload,
    WikiArticleUpdatePayload, WikiArticlePictureInfo,
    WikiArticlePictureCreationPayload, WikiTopicPayload, WikiTopicInfo,
    WikiTopicTemplatePayload)


router = APIRouter(
    prefix="/wiki",
    responses={
        204: {"description": "Empty result"},
        404: {"description": "Not found"},
    },
    tags=["app/services/wiki"],
)


topic_param_path = Path(description="The name of the topic")


async def topic_or_abort(
        session: AsyncSession,
        name: str,
) -> WikiTopic:
    topic = await WikiTopic.get(session, name=name)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No topic(s) found"
        )
    return topic


async def article_or_abort(
        session: AsyncSession,
        topic: str,
        name: str,
) -> WikiArticle:
    article = await WikiArticle.get_latest_version(session, topic=topic, name=name)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No article(s) found"
        )
    return article


@router.get("/topics",
            response_model=list[WikiTopicInfo])
async def get_topics(
        limit: int = Query(default=50, description="The number of topics name to fetch"),
        session: AsyncSession = Depends(get_session),
):
    if limit > 50:
        limit = 50
    topics = await WikiTopic.get_multiple(session, limit=limit)
    return topics


@router.post("/topics/u",
             dependencies=[Depends(is_operator)])
async def create_topic(
        response: Response,
        payload: WikiTopicPayload = Body(description="The new topic information"),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiTopic.create(session, name=payload.name)
        return ResultResponse(
            msg=f"A new wiki topic '{payload.name}' was successfully created.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create the wiki topic '{payload.name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/topics/u/{topic_name}",
            response_model=list[WikiArticleInfo])
async def get_topic_articles(
        topic_name: str = topic_param_path,
        limit: int = Query(
            default=50, description="The number of articles name to fetch"),
        session: AsyncSession = Depends(get_session),
):
    if limit > 50:
        limit = 50
    await topic_or_abort(session, name=topic_name)
    articles = await WikiArticle.get_by_topic(session, topic=topic_name, limit=limit)
    return articles


@router.delete("/topics/u/{topic_name}",
               dependencies=[Depends(is_operator)])
async def delete_topic(
        response: Response,
        topic_name: str = topic_param_path,
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiTopic.delete(session, name=topic_name)
        return ResultResponse(
            msg=f"Wiki topic '{topic_name}' was successfully deleted.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to delete wiki topic '{topic_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/topics/u/{topic_name}/template",
            response_model=str)
async def get_topic_template(
        topic_name: str = topic_param_path,
        session: AsyncSession = Depends(get_session),
):
    topic = await topic_or_abort(session, name=topic_name)
    try:
        template = await topic.get_template()
        return template
    except WikiArticleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND)


@router.post("/topics/u/{topic_name}/template",
             dependencies=[Depends(is_operator)])
async def create_topic_template(
        response: Response,
        payload: WikiTopicTemplatePayload = Body(description="The new topic template"),
        topic_name: str = topic_param_path,
        session: AsyncSession = Depends(get_session),
):
    topic = await topic_or_abort(session, name=topic_name)
    try:
        await topic.create_template(payload.content)
        return ResultResponse(
            msg=f"A new template for topic '{topic_name}' was created",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.post("/topics/u/{topic_name}/template/upload_file",
             dependencies=[Depends(is_operator)])
async def create_topic_template(
        response: Response,
        file: UploadFile,
        topic_name: str = topic_param_path,
        session: AsyncSession = Depends(get_session),
):
    if not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File should be a valid '.md' file"
        )
    topic = await topic_or_abort(session, name=topic_name)
    try:
        content = await file.read()
        await topic.create_template(content.decode("utf-8"))
        return ResultResponse(
            msg=f"A new template for topic '{topic_name}' was created",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.post("/topics/u/{topic_name}/u",
             dependencies=[Depends(is_operator)])
async def create_topic_article(
        response: Response,
        payload: WikiArticleCreationPayload = Body(description="The new article"),
        topic_name: str = topic_param_path,
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiArticle.create(
            session, topic=topic_name, name=payload.name,
            content=payload.content, author_id=current_user.id)
        return ResultResponse(
            msg=f"A new wiki article was successfully created.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.post("/topics/u/{topic_name}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_article(
        response: Response,
        file: UploadFile,
        topic_name: str = topic_param_path,
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File should be a valid '.md' file"
        )
    filename = file.filename.rstrip(".md")
    try:
        if file.size > MAX_TEXT_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Picture file too large"
            )
        content = await file.read()
        await WikiArticle.create(
            session, topic=topic_name, name=filename,
            content=content.decode("utf-8"), author_id=current_user.id)
        return ResultResponse(
            msg=f"A new wiki article was successfully uploaded.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to upload a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/topics/u/{topic_name}/u/{article_name}",
            response_model=WikiArticleInfo)
async def get_topic_article(
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        session: AsyncSession = Depends(get_session),
):
    article = await article_or_abort(session, topic=topic_name, name=article_name)
    return article


@router.put("/topics/u/{topic_name}/u/{article_name}",
            dependencies=[Depends(is_operator)])
async def update_topic_article(
        response: Response,
        payload: WikiArticleUpdatePayload = Body(description="The updated article"),
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiArticle.update(
            session, topic=topic_name, name=article_name,
            content=payload.content, author_id=current_user.id)
        return ResultResponse(
            msg=f"Wiki article '{article_name}' was successfully updated.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to update wiki article '{article_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.delete("/topics/u/{topic_name}/u/{article_name}",
               dependencies=[Depends(is_operator)])
async def delete_topic_article(
        response: Response,
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiArticle.delete(
            session, topic=topic_name, name=article_name,
            author_id=current_user.id)
        return ResultResponse(
            msg=f"Wiki article '{article_name}' was successfully deleted.",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to delete wiki article '{article_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/topics/u/{topic_name}/u/{article_name}/history",
            response_model=list[WikiArticleModificationInfo])
async def get_topic_article_history(
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        session: AsyncSession = Depends(get_session),
):
    article = await article_or_abort(session, topic=topic_name, name=article_name)
    history = await WikiArticleModification.get_for_article(
        session, article_id=article.id)
    return history


@router.post("/topics/u/{topic_name}/u/{article_name}/u",
             dependencies=[Depends(is_operator)])
async def add_picture_to_article(
        response: Response,
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        payload: WikiArticlePictureCreationPayload = Body(description="The new picture"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiArticlePicture.create(
            session, topic=topic_name, article=article_name, name=payload.name,
            content=payload.content,
            author_id=current_user.id)
        return ResultResponse(
            msg=f"A new wiki picture was successfully created.",
            status=ResultStatus.success
        )
    except WikiArticleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No article(s) found"
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.post("/topics/u/{topic_name}/u/{article_name}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_picture_to_article(
        response: Response,
        file: UploadFile,
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File should be a valid '.md' file"
        )
    filename = file.filename.rstrip(".md")
    try:
        if file.size > MAX_PICTURE_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Picture file too large"
            )
        content = await file.read()
        await WikiArticlePicture.create(
            session, topic=topic_name, article=article_name, name=filename,
            content=content, author_id=current_user.id)
        return ResultResponse(
            msg=f"A new wiki picture was successfully uploaded.",
            status=ResultStatus.success
        )
    except WikiArticleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No article(s) found"
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to upload a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/topics/u/{topic_name}/u/{article_name}/u/{picture_name}",
            response_model=WikiArticlePictureInfo)
async def get_article_picture(
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        picture_name: str = Path(description="The name of the picture"),
        session: AsyncSession = Depends(get_session),
):
    try:
        picture = await WikiArticlePicture.get(
            session, topic=topic_name, article=article_name, name=picture_name)
    except WikiArticleNotFound:
        picture = None
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No picture(s) found"
        )
    return picture


@router.delete("/topics/u/{topic_name}/u/{article_name}/u/{picture_name}",
               dependencies=[Depends(is_operator)])
async def delete_picture_from_article(
        response: Response,
        topic_name: str = topic_param_path,
        article_name: str = Path(description="The name of the article"),
        picture_name: str = Path(description="The name of the picture"),
        session: AsyncSession = Depends(get_session),
):
    try:
        await WikiArticlePicture.delete(
            session, topic=topic_name, article=article_name, name=picture_name)
        return ResultResponse(
            msg=f"The wiki picture '{picture_name}' was successfully deleted.",
            status=ResultStatus.success
        )
    except WikiArticleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No article(s) found"
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to delete the wiki picture '{picture_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/articles",
            response_model=list[WikiArticleInfo])
async def get_articles(
        topic: list[str] = Query(default=None, description="The name of the topics"),
        name: list[str] = Query(default=None, description="The name of the articles"),
        limit: int = Query(default=50, description="The number of articles name to fetch"),
        session: AsyncSession = Depends(get_session),
):
    articles = await WikiArticle.get_multiple(
        session, topic=topic, name=name, limit=limit)
    return articles
