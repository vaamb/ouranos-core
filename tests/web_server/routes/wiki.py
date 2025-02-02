from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import (
    WikiArticle, WikiArticleModification, WikiArticlePicture, WikiTopic)

from tests.data.app import (
    wiki_article_content, wiki_article_name, wiki_picture_name, wiki_topic_name)
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
    response = client.get(f"/api/app/services/wiki/topics/u/{wiki_topic_name}/articles")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert wiki_article_name in [article["name"] for article in data]


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
    name = "New article name"
    content = "New article content"
    payload = {
        "name": name,
        "content": content,
    }
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get(
            session, topic_name=wiki_topic_name, name=name)
        assert article.name == name
        assert content == await article.get_content()

    # Clean up test
    async with db.scoped_session() as session:
        await WikiArticle.delete(
            session, topic_name=wiki_topic_name, name=name, author_id=operator.id)


@pytest.mark.asyncio
async def test_get_article(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_name}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["topic"] == wiki_topic_name
    assert data["name"] == wiki_article_name


@pytest.mark.asyncio
async def test_update_article_unauthorized(client: TestClient):
    response = client.put(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_name}")
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
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_name}",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get(
            session, topic_name=wiki_topic_name, name=wiki_article_name)
        assert article.name == wiki_article_name
        assert content == await article.get_content()

    # Partly clean up test
    async with db.scoped_session() as session:
        latest = await WikiArticleModification.get_latest_version(
            session, article_id=article.id)
        if latest:
            await WikiArticleModification.delete(
                session, article_id=article.id, version=latest.version)


@pytest.mark.asyncio
async def test_delete_article_unauthorized(client: TestClient):
    response = client.delete(f"/api/app/services/wiki/topics/u/{wiki_topic_name}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_article(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    article_name = "To delete article"
    # Setup test
    async with db.scoped_session() as session:
        await WikiArticle.create(
            session,
            topic_name=wiki_topic_name,
            name=article_name,
            values={
                "content": "",
                "author_id": operator.id,
            },
        )

    # Run test
    response = client_operator.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{article_name}")
    assert response.status_code == 200

    async with db.scoped_session() as session:
        article = await WikiArticle.get(
            session, topic_name=wiki_topic_name, name=article_name)
        assert article is None


@pytest.mark.asyncio
async def test_get_article_history(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_name}/history")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert data[0]["topic"] == wiki_topic_name
    assert data[0]["article"] == wiki_article_name
    assert data[0]["version"] == 1
    assert data[0]["author_id"] == operator.id


@pytest.mark.asyncio
async def test_create_picture_unauthorized(client: TestClient):
    response = client.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/u/{wiki_article_name}/u")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_picture_invalid_name(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    name = "invalid.name"
    content = b"def not a true picture"
    payload = {
        "name": name,
        "extension": ".jpeg",
        "content": content.decode("utf-8"),
    }
    # Run test
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_name}/u",
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_picture(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    name = "Cute plant picture"
    content = b"def not a true picture"
    payload = {
        "name": name,
        "extension": ".jpeg",
        "content": content.decode("utf-8"),
    }
    # Run test
    response = client_operator.post(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_name}/u",
        json=payload,
    )
    assert response.status_code == 200

    async with db.scoped_session() as session:
        picture = await WikiArticlePicture.get(
            session, topic_name=wiki_topic_name, article_name=wiki_article_name,
            name=name)
        assert picture.name == name
        assert content == await picture.get_image()

        # Clean up test
        await WikiArticlePicture.delete(
            session, topic_name=wiki_topic_name, article_name=wiki_article_name,
            name=name)


@pytest.mark.asyncio
async def test_get_picture(client: TestClient):
    response = client.get(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_name}/u/{wiki_picture_name}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["topic"] == wiki_topic_name
    assert data["article"] == wiki_article_name
    assert data["name"] == wiki_picture_name


@pytest.mark.asyncio
async def test_delete_picture_unauthorized(client: TestClient):
    response = client.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_name}/u/{wiki_picture_name}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_picture(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    picture_name = "to_delete_picture"
    # Setup test
    async with db.scoped_session() as session:
        await WikiArticlePicture.create(
            session,
            topic_name=wiki_topic_name,
            article_name=wiki_article_name,
            name=picture_name,
            values={
                "extension": ".png",
                "content": b"",
            },
        )

    # Run test
    response = client_operator.delete(
        f"/api/app/services/wiki/topics/u/{wiki_topic_name}/"
        f"u/{wiki_article_name}/u/{picture_name}")
    assert response.status_code == 200

    async with db.scoped_session() as session:
        picture = await WikiArticlePicture.get(
            session, topic_name=wiki_topic_name, article_name=wiki_article_name,
            name=picture_name)
        assert picture is None


@pytest.mark.asyncio
async def test_get_articles(client: TestClient):
    response = client.get(f"/api/app/services/wiki/articles")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 1
    assert wiki_article_name in [article["name"] for article in data]
