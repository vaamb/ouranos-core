from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, Form, HTTPException, Query, Path, status, UploadFile)
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config.consts import (
    MAX_PICTURE_FILE_SIZE, MAX_TEXT_FILE_SIZE, SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_TEXT_EXTENSIONS)
from ouranos.core.database.models.app import (
    ServiceName, UserMixin, WikiArticleNotFound, WikiArticle, WikiArticleModification,
    WikiPicture, WikiTag, WikiTopic)
from ouranos.core.utils import check_filename
from ouranos.web_server.auth import get_current_user, is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.services.utils import service_enabled
from ouranos.web_server.validate.wiki import (
    WikiArticleInfo, WikiArticleModificationInfo, WikiArticleCreationPayload,
    WikiArticleUpdatePayload,
    WikiArticlePictureInfo, WikiArticlePictureCreationPayload,
    WikiTagCreationPayload, WikiTagInfo, WikiTagUpdatePayload,
    WikiTopicCreationPayload, WikiTopicInfo, WikiTopicTemplatePayload,
    WikiTopicUpdatePayload)


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
        slug: str,
) -> WikiTopic:
    topic = await WikiTopic.get(session, slug=slug)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No topic(s) found"
        )
    return topic


async def article_or_abort(
        session: AsyncSession,
        topic_slug: str,
        slug: str,
) -> WikiArticle:
    article = await WikiArticle.get(session, topic_slug=topic_slug, slug=slug)
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
        return f"A new wiki tag '{payload.name}' was successfully created.",
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create the wiki tag '{payload.name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.put("/tags/u/{tag_slug}",
            dependencies=[Depends(is_operator)])
async def update_tag(
        tag_slug: Annotated[str, Path(description="The name of the tag")],
        payload: Annotated[
            WikiTagUpdatePayload,
            Body(description="The tag updated information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        wiki_tag_dict = payload.model_dump(exclude_defaults=True)
        await WikiTag.update(
            session,
            name=tag_slug,
            values=wiki_tag_dict,
        )
        return f"Wiki tag '{tag_slug}' was successfully updated."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki tag '{tag_slug}'. Error msg: "
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
        return f"A new wiki topic '{payload.name}' was successfully created."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create the wiki topic '{payload.name}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_slug}",
            response_model=WikiTopicInfo)
async def get_topic(
        *,
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    return topic


@router.put("/topics/u/{topic_slug}",
               dependencies=[Depends(is_operator)])
async def update_topic(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiTopicUpdatePayload,
            Body(description="The topic updated information"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        wiki_topic_dict = payload.model_dump(by_alias=True, exclude_defaults=True)
        await WikiTopic.update(
            session,
            name=topic.name,
            values=wiki_topic_dict,
        )
        return f"Wiki topic '{topic_slug}' was successfully updated.",
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki topic '{topic_slug}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/topics/u/{topic_slug}",
               dependencies=[Depends(is_operator)])
async def delete_topic(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        await WikiTopic.delete(session, name=topic.name)
        return f"Wiki topic '{topic_slug}' was successfully deleted.",
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete wiki topic '{topic_slug}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_slug}/articles",
            response_model=list[WikiArticleInfo])
async def get_topic_articles(
        *,
        topic_slug: Annotated[str, Path(description="The name of the topic")],
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
    await topic_or_abort(session, slug=topic_slug)
    articles = await WikiArticle.get_multiple(
        session, topic_slug=topic_slug, tags_name=tags, limit=limit)
    return articles


@router.get("/topics/u/{topic_slug}/template",
            response_model=str)
async def get_topic_template(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        template = await topic.get_template()
        return template
    except WikiArticleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND)


@router.post("/topics/u/{topic_slug}/template",
             dependencies=[Depends(is_operator)])
async def create_topic_template(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiTopicTemplatePayload,
            Body(description="The new topic template"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        await topic.create_template(payload.content)
        return f"A new template for topic '{topic_slug}' was created"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_slug}/template/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_topic_template(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        file: UploadFile,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File should be a valid '.md' file"
        )
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        content = await file.read()
        await topic.create_template(content.decode("utf-8"))
        return f"A new template for topic '{topic_slug}' was created"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki template. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_slug}/u",
             dependencies=[Depends(is_operator)])
async def create_article(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        payload: Annotated[
            WikiArticleCreationPayload,
            Body(description="The new article"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        wiki_article_dict = payload.model_dump(by_alias=True)
        name = wiki_article_dict.pop("name")
        await WikiArticle.create(
            session,
            topic_name=topic.name,
            name=name,
            values={
                **wiki_article_dict,
                "author_id": current_user.id,
            },
        )
        return f"A new wiki article was successfully created."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_slug}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_article(
        *,
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        name: Annotated[str, Form()] = None,
        description: Annotated[str, Form()] = None,
        tags: Annotated[list[str], Form()] = None,
        file: UploadFile,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        check_filename(file.filename, SUPPORTED_TEXT_EXTENSIONS)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{e}"
        )
    topic = await topic_or_abort(session, slug=topic_slug)
    try:
        if file.size > MAX_TEXT_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Picture file too large"
            )
        content = await file.read()
        await WikiArticle.create(
            session,
            topic_slug=topic.slug,
            name=name or file.filename.split(".")[0],
            values={
                "description": description,
                "tags": tags,
                "content": content.decode("utf-8"),
                "author_id": current_user.id,
            },
        )
        return "A new wiki article was successfully uploaded."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to upload a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_slug}/u/{article_slug}",
            response_model=WikiArticleInfo)
async def get_article(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    return article


@router.put("/topics/u/{topic_slug}/u/{article_slug}",
            dependencies=[Depends(is_operator)])
async def update_article(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        payload: Annotated[
            WikiArticleUpdatePayload,
            Body(description="The article updated information")
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    try:
        wiki_article_dict = payload.model_dump(by_alias=True, exclude_defaults=True)
        await WikiArticle.update(
            session,
            topic_name=article.topic_name,
            name=article.name,
            values={
                **wiki_article_dict,
                "author_id": current_user.id,
            },
        )
        return f"Wiki article '{article_slug}' was successfully updated."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update wiki article '{article_slug}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/topics/u/{topic_slug}/u/{article_slug}",
               dependencies=[Depends(is_operator)])
async def delete_article(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    try:
        await WikiArticle.delete(
            session, topic_name=article.topic_name, name=article.name,
            author_id=current_user.id)
        return f"Wiki article '{article_slug}' was successfully deleted."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete wiki article '{article_slug}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.put("/topics/u/{topic_slug}/u/{article_slug}/upload_file",
            dependencies=[Depends(is_operator)])
async def update_article_upload(
        *,
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        description: Annotated[str, Form()] = None,
        tags: Annotated[list[str], Form()] = None,
        file: UploadFile,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        check_filename(file.filename, SUPPORTED_TEXT_EXTENSIONS)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{e}"
        )
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    try:
        if file.size > MAX_TEXT_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Picture file too large"
            )
        content = await file.read()
        await WikiArticle.update(
            session,
            topic_name=article.topic_name,
            name=article.name,
            values={
                "description": description,
                "tags": tags,
                "content": content.decode("utf-8"),
                "author_id": current_user.id,
            },
        )
        return "A new wiki article was successfully uploaded."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to upload a new wiki article. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_slug}/u/{article_slug}/history",
            response_model=list[WikiArticleModificationInfo])
async def get_article_history(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    history = await WikiArticleModification.get_multiple(
        session, article_id=article.id, order_by=WikiArticleModification.version.desc())
    return history


@router.get("/topics/u/{topic_slug}/u/{article_slug}/pictures",
            response_model=list[WikiArticlePictureInfo])
async def get_article_pictures(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    pictures = await WikiPicture.get_multiple(
        session, topic_slug=topic_slug, article_slug=article_slug)
    return pictures


@router.post("/topics/u/{topic_slug}/u/{article_slug}/u",
             dependencies=[Depends(is_operator)])
async def add_picture(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        payload: Annotated[
            WikiArticlePictureCreationPayload,
            Body(description="The new picture"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    try:
        wiki_picture_dict = payload.model_dump(by_alias=True)
        await WikiPicture.create(
            session,
            topic_name=article.topic_name,
            article_name=article.name,
            name=wiki_picture_dict.pop("name"),
            values=wiki_picture_dict,
        )
        return "A new wiki picture was successfully created."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.post("/topics/u/{topic_slug}/u/{article_slug}/u/upload_file",
             dependencies=[Depends(is_operator)])
async def upload_picture(
        *,
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        name: Annotated[str, Form()],
        description: Annotated[str, Form()] = None,
        tags: Annotated[list[str], Form()] = None,
        file: UploadFile,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        check_filename(file.filename, SUPPORTED_IMAGE_EXTENSIONS)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{e}"
        )
    article = await article_or_abort(session, topic_slug=topic_slug, slug=article_slug)
    try:
        if file.size > MAX_PICTURE_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Picture file too large"
            )
        await WikiPicture.create(
            session,
            topic_name=article.topic_name,
            article_name=article.name,
            name=name or file.filename.split(".")[0],
            values={
                "description": description,
                "tags": tags,
                "content": await file.read(),
                "extension": file.filename.split(".")[1],
            },
        )
        return f"A new wiki picture was successfully uploaded."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new wiki article picture. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/topics/u/{topic_slug}/u/{article_slug}/u/{picture_slug}",
            response_model=WikiArticlePictureInfo)
async def get_picture(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        picture_slug: Annotated[str, Path(description="The name of the picture")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    picture = await WikiPicture.get(
        session, topic_slug=topic_slug, article_slug=article_slug, slug=picture_slug)
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No picture found"
        )
    return picture


@router.delete("/topics/u/{topic_slug}/u/{article_slug}/u/{picture_slug}",
               dependencies=[Depends(is_operator)])
async def delete_picture(
        topic_slug: Annotated[str, Path(description="The name of the topic")],
        article_slug: Annotated[str, Path(description="The name of the article")],
        picture_slug: Annotated[str, Path(description="The name of the picture")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    picture = await WikiPicture.get(
        session, topic_slug=topic_slug, article_slug=article_slug,
        slug=picture_slug)
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No picture(s) found"
        )
    try:
        await WikiPicture.delete(
            session, topic_name=picture.topic_name, article_name=picture.article_name,
            name=picture.name)
        return f"The wiki picture '{picture_slug}' was successfully deleted."
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete the wiki picture '{picture_slug}'. Error msg: "
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
