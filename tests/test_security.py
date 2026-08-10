from flask import Flask, jsonify

import services.security_service as security


def make_app(tmp_path):
    security.DB_PATH = str(tmp_path / "security.db")
    app = Flask(__name__)
    app.config.update(
        TESTING=True, PUBLIC_DEPLOYMENT=False, SECURITY_ADMIN_TOKEN="", MAX_CONTENT_LENGTH=64
    )

    @app.post("/api/run-picks")
    def mutate():
        return jsonify(status="success")

    security.init_security(app)
    return app


def test_security_headers_and_health(tmp_path):
    client = make_app(tmp_path).test_client()
    response = client.get("/api/security-health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_mutation_requires_post_and_custom_header(tmp_path):
    client = make_app(tmp_path).test_client()
    assert client.get("/api/run-picks").status_code == 405
    assert client.post("/api/run-picks").status_code == 403
    assert (
        client.post("/api/run-picks", headers={"X-Requested-With": "Jingleez"}).status_code == 200
    )


def test_cross_site_mutation_is_blocked(tmp_path):
    client = make_app(tmp_path).test_client()
    response = client.post(
"/api/run-picks",
        headers={
"X-Requested-With": "Jingleez",
"Origin": "https://attacker.example",
        },
    )
    assert response.status_code == 403
