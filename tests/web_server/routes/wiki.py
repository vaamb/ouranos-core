from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import (
    WikiArticle, WikiArticleModification, WikiPicture, WikiTopic)
from ouranos.core.utils import slugify

from tests.data.app import (
    wiki_article_content, wiki_article_name, wiki_picture_name, wiki_topic_name)
from tests.data.auth import operator
from class_fixtures import ServicesEnabled, UsersAware, WikiAware


@pytest.mark.asyncio
class TestWikiTopics(ServicesEnabled, UsersAware, WikiAware):
    async def test_get_topics(self, client: TestClient, db: AsyncSQLAlchemyWrapper):
        response = client.get("/api/app/services/wiki/topics")
        assert response.status_code == 200

        data = json.loads(response.text)
        topic = data[0]
        async with db.scoped_session() as session:
            topics = await WikiTopic.get_multiple(session)
            assert topic["name"] == topics[0].name
            assert topic["path"] == str(topics[0].path)

    async def test_create_topic_unauthorized(self, client: TestClient):
        response = client.post("/api/app/services/wiki/topics/u")
        assert response.status_code == 403

    async def test_create_topic(
            self,
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

    async def test_get_topic_articles(self, client: TestClient):
        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/articles")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert wiki_article_name in [article["name"] for article in data]

    async def test_delete_topic_unauthorized(self, client: TestClient):
        response = client.delete(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}")
        assert response.status_code == 403

    async def test_delete_topic(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        name = "To delete topic"
        # Setup test
        async with db.scoped_session() as session:
            await WikiTopic.create(session, name=name)

        # Run test
        response = client_operator.delete(
            f"/api/app/services/wiki/topics/u/{slugify(name)}")
        assert response.status_code == 200

        async with db.scoped_session() as session:
            topics = await WikiTopic.get_multiple(session)
            assert len(topics) == 1

    async def test_get_topic_template(self, client: TestClient):
        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/template")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data == wiki_article_content

    async def test_set_topic_template_unauthorized(self, client: TestClient):
        response = client.post(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/template")
        assert response.status_code == 403

    async def test_set_topic_template(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        template = "Test new template"
        payload = {
            "content": template
        }
        response = client_operator.post(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/template",
            json=payload,
        )
        assert response.status_code == 200

        async with db.scoped_session() as session:
            topic = await WikiTopic.get(session, name=wiki_topic_name)
            topic_template = await topic.get_template()
            assert topic_template == template


@pytest.mark.asyncio
class TestWikiArticles(ServicesEnabled, UsersAware, WikiAware):
    async def test_get_articles(self, client: TestClient):
        response = client.get("/api/app/services/wiki/articles")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert wiki_article_name in [article["name"] for article in data]

    async def test_create_article_unauthorized(self, client: TestClient):
        response = client.post(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/u")
        assert response.status_code == 403

    async def test_create_article(
            self,
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
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/u",
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

    async def test_get_article(self, client: TestClient):
        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["topic"] == wiki_topic_name
        assert data["name"] == wiki_article_name

    async def test_update_article_unauthorized(self, client: TestClient):
        response = client.put(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}")
        assert response.status_code == 403

    async def test_update_article(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper
    ):
        content = "Updated article content"
        payload = {
            "content": content,
        }
        # Run test
        response = client_operator.put(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}",
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

    async def test_delete_article_unauthorized(self, client: TestClient):
        response = client.delete(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}")
        assert response.status_code == 403

    async def test_delete_article(
            self,
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
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(article_name)}")
        assert response.status_code == 200

        async with db.scoped_session() as session:
            article = await WikiArticle.get(
                session, topic_name=wiki_topic_name, name=article_name)
            assert article is None

    async def test_get_article_history(self, client: TestClient):
        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/history")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["topic"] == wiki_topic_name
        assert data[0]["article"] == wiki_article_name
        assert data[0]["version"] == 1
        assert data[0]["author_id"] == operator.id


@pytest.mark.asyncio
class TestWikiPictures(ServicesEnabled, UsersAware, WikiAware):
    async def test_create_picture_unauthorized(self, client: TestClient):
        response = client.post(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u")
        assert response.status_code == 403

    async def test_create_picture_invalid_name(
            self,
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
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{wiki_article_name}/u",
            json=payload,
        )
        assert response.status_code == 404

    async def test_create_picture(
            self,
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
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u",
            json=payload,
        )
        assert response.status_code == 200

        async with db.scoped_session() as session:
            picture = await WikiPicture.get(
                session, topic_name=wiki_topic_name, article_name=wiki_article_name,
                name=name)
            assert picture.name == name
            assert content == await picture.get_image()

            # Clean up test
            await WikiPicture.delete(
                session, topic_name=wiki_topic_name, article_name=wiki_article_name,
                name=name)

    async def test_get_picture(self, client: TestClient):
        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u/{slugify(wiki_picture_name)}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["topic"] == wiki_topic_name
        assert data["article"] == wiki_article_name
        assert data["name"] == wiki_picture_name

    async def test_delete_picture_unauthorized(self, client: TestClient):
        response = client.delete(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u/{slugify(wiki_picture_name)}")
        assert response.status_code == 403

    async def test_delete_picture(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        picture_name = "to_delete_picture"
        # Setup test
        async with db.scoped_session() as session:
            await WikiPicture.create(
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
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u/{slugify(picture_name)}")
        assert response.status_code == 200

        async with db.scoped_session() as session:
            picture = await WikiPicture.get(
                session, topic_name=wiki_topic_name, article_name=wiki_article_name,
                name=picture_name)
            assert picture is None

@pytest.mark.asyncio
class TestWikiNotFound(ServicesEnabled, UsersAware, WikiAware):
    async def test_error_404(self, client: TestClient):
        wrong = "so wrong it doesn't match"

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}")
        assert response.status_code == 200

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wrong)}")
        assert response.status_code == 404

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}")
        assert response.status_code == 200

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wrong)}")
        assert response.status_code == 404

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wiki_article_name)}/u/{slugify(wiki_picture_name)}")
        assert response.status_code == 200

        response = client.get(
            f"/api/app/services/wiki/topics/u/{slugify(wiki_topic_name)}/"
            f"u/{slugify(wrong)}/u/{slugify(wiki_picture_name)}")
        assert response.status_code == 404
