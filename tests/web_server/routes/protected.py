from fastapi.testclient import TestClient

from tests.class_fixtures import UsersAware


class TestAuthenticatedProtection(UsersAware):
    def test_access_auth_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_authenticated")
        assert response.status_code == 403

    def test_access_auth_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_auth_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_auth_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'


class TestOperatorProtection(UsersAware):
    def test_access_operator_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_operator")
        assert response.status_code == 403

    def test_access_operator_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_operator")
        assert response.status_code == 403

    def test_access_operator_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_operator")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_operator_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_operator")
        assert response.status_code == 200
        assert response.text == '"Success"'


class TestAdminProtection(UsersAware):
    def test_access_admin_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_admin")
        assert response.status_code == 200
        assert response.text == '"Success"'
