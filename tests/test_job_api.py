from app.services.job_service import JobService
from tests.test_auth_api import _build_test_client, _csrf_headers, _login, _upload_video_asset


def test_get_job_returns_404_when_missing(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.get("/api/jobs/not_exists")
        assert response.status_code == 404


def test_get_job_success(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        asset_id = _upload_video_asset(client)
        job = JobService().create_job(
            job_type="video_analysis",
            input_asset_id=asset_id,
            status="succeeded",
            progress=100,
            result={"motion_asset_count": 3},
        )

        response = client.get(f"/api/jobs/{job['id']}")
        assert response.status_code == 200
        body = response.json()

        assert body["data"]["id"] == job["id"]
        assert body["data"]["job_type"] == "video_analysis"
        assert body["data"]["status"] in {"queued", "running", "succeeded"}
