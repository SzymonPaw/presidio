from src.app_factory import create_app


def test_privacy_policy_page_exists():
    app = create_app()
    client = app.test_client()

    response = client.get("/polityka-prywatnosci/")

    assert response.status_code == 200
    assert b"Polityka prywatno\xc5\x9bci" in response.data
