from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Query, Path, status, UploadFile)
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config.consts import MAX_PICTURE_FILE_SIZE, MAX_TEXT_FILE_SIZE
from ouranos.core.database.models.app import (
    ServiceName, UserMixin, WikiArticleNotFound, WikiArticle, WikiArticleModification,
    WikiArticlePicture, WikiTag, WikiTopic)
from ouranos.web_server.auth import get_current_user, is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.services.utils import service_enabled
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.wiki import (
    WikiArticleInfo, WikiArticleModificationInfo, WikiArticleCreationPayload,
    WikiArticleUpdatePayload, WikiArticlePictureInfo,
    WikiArticlePictureCreationPayload, WikiTagCreationPayload, WikiTagInfo,
    WikiTagUpdatePayload, WikiTopicCreationPayload, WikiTopicInfo,
    WikiTopicTemplatePayload, WikiTopicUpdatePayload)


router = APIRouter(
    prefix="/wiki",
    responses={
        204: {"description": "Empty result"},
        404: {"description": "Not found"},
    },
    dependencies=[Depends(service_enabled(ServiceName.wiki))],
    tags=["app/services/wiki"],
)


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
    article = await WikiArticle.get(session, topic_name=topic, name=name)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No article(s) found"
        )
    return article


@router.get("/tags",
            response_model=list[WikiTagInfo])
async def get_tags(
        *,
        limit: Annotated[
            int,
            Query(description="The number of tags name to fetch")
        ] = 100,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if limit > 100:
        limit = 100
    tags = await WikiTag.get_multiple(session, limit=limit)
    return tags


@router.post("/tags/u",
             dependencies=[Depends(is_operator)])
async def create_tag(
        payload: Annotated[
            WikiTagCreationPayload,
            Body(description="The new tag information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_tag_dict = payload.model_dump()
        name = wiki_tag_dict.pop("name")
        await WikiTag.create(
            session,
            name=name,
            values=wiki_tag_dict,
        )
        return ResultResponse(
            msg=f"A new wiki tag '{payload.name}' was successfully created.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create the wiki tag '{payload.name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.put("/tags/u/{tag_name}",
            dependencies=[Depends(is_operator)])
async def update_tag(
        tag_name: Annotated[str, Path(description="The name of the tag")],
        payload: Annotated[
            WikiTagUpdatePayload,
            Body(description="The updated tag information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_tag_dict = payload.model_dump(exclude_defaults=True)
        await WikiTag.update(
            session,
            name=tag_name,
            values=wiki_tag_dict,
        )
        return ResultResponse(
            msg=f"Wiki tag '{tag_name}' was successfully updated.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki tag '{tag_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics",
            response_model=list[WikiTopicInfo])
async def get_topics(
        *,
        tags: Annotated[
            list[str] | None,
            Query(description="The tags of the topics"),
        ] = None,
        limit: Annotated[
            int,
            Query(description="The number of topics name to fetch")
        ] = 50,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if limit > 50:
        limit = 50
    topics = await WikiTopic.get_multiple(session, tags_name=tags, limit=limit)
    return topics


@router.post("/topics/u",
             dependencies=[Depends(is_operator)])
async def create_topic(
        payload: Annotated[
            WikiTopicCreationPayload,
            Body(description="The new topic information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_topic_dict = payload.model_dump(by_alias=True)
        name = wiki_topic_dict.pop("name")
        await WikiTopic.create(
            session,
            name=name,
            values=wiki_topic_dict,
        )
        return ResultResponse(
            msg=f"A new wiki topic '{payload.name}' was successfully created.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create the wiki topic '{payload.name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_name}",
            response_model=list[WikiArticleInfo])
async def get_topic_articles(
        *,
        topic_name: Annotated[str, Path(description="The name of the topic")],
        tags: Annotated[
            list[str] | None,
            Query(description="The tags of the articles"),
        ] = None,
        limit: Annotated[
            int,
            Query(description="The number of articles name to fetch")
        ] = 50,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if limit > 50:
        limit = 50
    await topic_or_abort(session, name=topic_name)
    articles = await WikiArticle.get_multiple(
        session, topic_name=topic_name, tags_name=tags, limit=limit)
    return articles


@router.put("/topics/u/{topic_name}",
               dependencies=[Depends(is_operator)])
async def update_topic(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiTopicUpdatePayload,
            Body(description="The new topic information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_topic_dict = payload.model_dump(by_alias=True, exclude_defaults=True)
        await WikiTopic.update(
            session,
            name=topic_name,
            values=wiki_topic_dict,
        )
        return ResultResponse(
            msg=f"Wiki topic '{topic_name}' was successfully updated.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki topic '{topic_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/topics/u/{topic_name}",
               dependencies=[Depends(is_operator)])
async def delete_topic(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        await WikiTopic.delete(session, name=topic_name)
        return ResultResponse(
            msg=f"Wiki topic '{topic_name}' was successfully deleted.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete wiki topic '{topic_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_name}/template",
            response_model=str)
async def get_topic_template(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        session: Annotated[AsyncSession, Depends(get_session)],
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
        topic_name: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiTopicTemplatePayload,
            Body(description="The new topic template"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, name=topic_name)
    try:
        await topic.create_template(payload.content)
        return ResultResponse(
            msg=f"A new template for topic '{topic_name}' was created",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_name}/template/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_topic_template(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        file: UploadFile,
        session: Annotated[AsyncSession, Depends(get_session)],
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_name}/u",
             dependencies=[Depends(is_operator)])
async def create_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiArticleCreationPayload,
            Body(description="The new article"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_article_dict = payload.model_dump(by_alias=True)
        name = wiki_article_dict.pop("name")
        await WikiArticle.create(
            session,
            topic_name=topic_name,
            name=name,
            values={
                **wiki_article_dict,
                "author_id": current_user.id,
            },
        )
        return ResultResponse(
            msg=f"A new wiki article was successfully created.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_name}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        file: UploadFile,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
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
            session,
            topic_name=topic_name,
            name=filename,
            values={
                "content": content.decode("utf-8"),
                "author_id": current_user.id,
            },
        )
        return ResultResponse(
            msg=f"A new wiki article was successfully uploaded.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to upload a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_name}/u/{article_name}",
            response_model=WikiArticleInfo)
async def get_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic=topic_name, name=article_name)
    return article


@router.put("/topics/u/{topic_name}/u/{article_name}",
            dependencies=[Depends(is_operator)])
async def update_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        payload: Annotated[
            WikiArticleUpdatePayload,
            Body(description="The updated article")
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_article_dict = payload.model_dump(by_alias=True, exclude_defaults=True)
        await WikiArticle.update(
            session,
            topic_name=topic_name,
            name=article_name,
            values={
                **wiki_article_dict,
                "author_id": current_user.id,
            },
        )
        return ResultResponse(
            msg=f"Wiki article '{article_name}' was successfully updated.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki article '{article_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/topics/u/{topic_name}/u/{article_name}",
               dependencies=[Depends(is_operator)])
async def delete_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        await WikiArticle.delete(
            session, topic_name=topic_name, name=article_name,
            author_id=current_user.id)
        return ResultResponse(
            msg=f"Wiki article '{article_name}' was successfully deleted.",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete wiki article '{article_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_name}/u/{article_name}/history",
            response_model=list[WikiArticleModificationInfo])
async def get_article_history(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic=topic_name, name=article_name)
    history = await WikiArticleModification.get_multiple(
        session, article_id=article.id, order_by=WikiArticleModification.version.desc())
    return history


@router.post("/topics/u/{topic_name}/u/{article_name}/u",
             dependencies=[Depends(is_operator)])
async def add_picture_to_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        payload: Annotated[
            WikiArticlePictureCreationPayload,
            Body(description="The new picture"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        await WikiArticlePicture.create(
            session, topic_name=topic_name, article_name=article_name, name=payload.name,
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_name}/u/{article_name}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_picture_to_article(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        file: UploadFile,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
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
            session, topic_name=topic_name, article_name=article_name, name=filename,
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_name}/u/{article_name}/u/{picture_name}",
            response_model=WikiArticlePictureInfo)
async def get_article_picture(
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        picture_name: Annotated[str, Path(description="The name of the picture")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        picture = await WikiArticlePicture.get(
            session, topic_name=topic_name, article_name=article_name,
            name=picture_name)
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
        topic_name: Annotated[str, Path(description="The name of the topic")],
        article_name: Annotated[str, Path(description="The name of the article")],
        picture_name: Annotated[str, Path(description="The name of the picture")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        await WikiArticlePicture.delete(
            session, topic_name=topic_name, article_name=article_name,
            name=picture_name)
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete the wiki picture '{picture_name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/articles",
            response_model=list[WikiArticleInfo])
async def get_articles(
        *,
        topic: Annotated[
            list[str] | None,
            Query(description="The name of the topics"),
        ] = None,
        name: Annotated[
              list[str] | None,
              Query(description="The name of the articles"),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Query(description="The tags of the articles"),
        ] = None,
        limit: Annotated[
            int,
            Query(description="The number of topics name to fetch")
        ] = 50,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    articles = await WikiArticle.get_multiple(
        session, topic_name=topic, name=name, tags_name=tags, limit=limit)
    return articles
