from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import (
    WikiArticle, WikiArticleModification, WikiArticlePicture, WikiTopic)

from tests.data.app import (
    wiki_article_content, wiki_article_title, wiki_picture_name, wiki_topic_name)
from tests.data.auth import operator


@pytest.mark.asyncio
async def test_get_topics(client: TestClient, db: AsyncSQLAlchemyWrapper):
    response = client.get("/api/app/services/wiki/topics")
    assert response.status_code == 200

    data = json.loads(response.text)
    topic = data[0]
    async with db.scoped_session() as session:
        topics = await WikiTopic.get_multiple(session)
        assert topic["name"] == topics[0].name
        assert topic["path"] == str(topics[0].path)


@pytest.mark.asyncio
async def test_create_topic_unauthorized(client: TestClient):
    response = client.post("/api/app/services/wiki/topics/u")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_topic(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper
):
    # Run test
    name = "Test topic"
    payload = {
        "name": name
    }
    response = client_operator.post(
        "/api/app/services/wiki/topics/u",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        topics = await WikiTopic.get_multiple(session)
        assert name in [topic.name for topic in topics]

    # Clean up test
    async with db.scoped_session() as session:
        await WikiTopic.delete(session, name=name)


@pytest.mark.asyncio
async def test_get_topic_articles(client: TestClient):
    response = client.get(f"/api/app/services/wiki/topics/u/{wiki_topic_name}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert wiki_article_title in [article["title"] for article in data]


@pytest.mark.asyncio
async def test_delete_topic_unauthorized(client: TestClient):
    response = client.delete(f"/api/app/services/wiki/topics/u/{wiki_topic_name}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_topic(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    name = "To delete topic"
    # Setup test
    async with db.scoped_session() as session:
        await WikiTopic.create(session, name=name)

    # Run test
    response = client_operator.delete(
        f"/api/app/services/wiki/topics/u/{name}")
    assert response.status_code == 200

    async with db.scoped_session() as session:
        topics = await WikiTopic.get_multiple(session)
        assert len(topics) == 1


@pytest.mark.asyncio
async def test_get_topic_template(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/template")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data == wiki_article_content


@pytest.mark.asyncio
async def test_set_topic_template_unauthorized(client: TestClient):
    response = client.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/template")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_set_topic_template(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    template = "Test new template"
    payload = {
        "content": template
    }
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/template",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        topic = await WikiTopic.get(session, name=wiki_topic_name)
        topic_template = await topic.get_template()
        assert topic_template == template


@pytest.mark.asyncio
async def test_create_article_unauthorized(client: TestClient):
    response = client.post(f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_article(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper
):
    # Run test
    title = "New article title"
    content = "New article content"
    payload = {
        "title": title,
        "content": content,
    }
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=title)
        assert article.title == title
        assert article.version == 1
        assert content == await article.get_content()

    # Clean up test
    async with db.scoped_session() as session:
        await WikiArticle.delete(
            session, topic=wiki_topic_name, title=title, author_id=operator.id)


@pytest.mark.asyncio
async def test_get_article(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_title}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["topic"] == wiki_topic_name
    assert data["title"] == wiki_article_title
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_update_article_unauthorized(client: TestClient):
    response = client.put(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_title}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_article(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper
):
    content = "Updated article content"
    payload = {
        "content": content,
    }
    # Run test
    response = client_operator.put(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_title}",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=wiki_article_title)
        assert article.title == wiki_article_title
        assert article.version == 2
        assert content == await article.get_content()

    # Partly clean up test
    async with db.scoped_session() as session:
        await WikiArticleModification.delete(
            session, article_id=article.id, article_version=article.version)


@pytest.mark.asyncio
async def test_delete_article_unauthorized(client: TestClient):
    response = client.delete(f"/api/app/services/wiki/topics/u/{wiki_topic_name}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_article(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    article_title = "To delete article"
    # Setup test
    async with db.scoped_session() as session:
        await WikiArticle.create(
            session, topic=wiki_topic_name, title=article_title, content="",
            author_id=operator.id)

    # Run test
    response = client_operator.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{article_title}")
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=article_title)
        assert article is None


@pytest.mark.asyncio
async def test_get_article_history(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_title}/history")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert data[0]["topic"] == wiki_topic_name
    assert data[0]["article"] == wiki_article_title
    assert data[0]["article_version"] == 1
    assert data[0]["author_id"] == operator.id


@pytest.mark.asyncio
async def test_create_picture_unauthorized(client: TestClient):
    response = client.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_title}/u")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_picture(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    name = "Cute plant picture"
    content = b"def not a true picture"
    payload = {
        "name": name,
        "content": content.decode("utf-8"),
    }
    # Run test
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_title}/u",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=wiki_article_title)
        picture = await WikiArticlePicture.get(
            session, article_obj=article, name=payload["name"])
        assert picture.name == name
        assert content == await picture.get_image()

    # Clean up test
    async with db.scoped_session() as session:
        await WikiArticlePicture.delete(session, article_obj=article, name=name)


@pytest.mark.asyncio
async def test_get_picture(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_title}/u/{wiki_picture_name}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["topic"] == wiki_topic_name
    assert data["article"] == wiki_article_title
    assert data["name"] == wiki_picture_name


@pytest.mark.asyncio
async def test_delete_picture_unauthorized(client: TestClient):
    response = client.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_title}/u/{wiki_picture_name}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_picture(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    picture_name = "To delete picture"
    # Setup test
    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=wiki_article_title)
        await WikiArticlePicture.create(
            session, article_obj=article, name=picture_name, content=b"",
            author_id=operator.id)

    # Run test
    response = client_operator.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_title}/u/{picture_name}")
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get_latest_version(
            session, topic=wiki_topic_name, title=wiki_article_title)
        picture = await WikiArticlePicture.get(
            session, article_obj=article, name=picture_name)
        assert picture is None


@pytest.mark.asyncio
async def test_get_articles(client: TestClient):
    response = client.get(f"/api/app/services/wiki/articles")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert wiki_article_title in [article["title"] for article in data]
