"""Customer websites: API, job queue and the deployer (with a fake docker and a local git repository)."""

import json
import os
import stat
import subprocess
import time

import pytest

from app.collector import deploy_exchange as dx
from app.collector import deployer
from app.core import config
from conftest import csrf_headers


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.fixture()
def sites_env(admin, tmp_path, monkeypatch):
    """Sites folder, exchange folder with a running 'deployer' flag, customers switched on."""
    sites = tmp_path / "sites"
    monkeypatch.setenv("XT_SITES_DIR", str(sites))
    monkeypatch.setenv("XT_EXCHANGE_DIR", str(tmp_path / "exchange"))
    config.get_settings.cache_clear()
    (dx.deploy_dir()).mkdir(parents=True)
    (dx.deploy_dir() / "alive").touch()
    admin.put("/api/features", json={"customers": True}, headers=csrf_headers(admin))
    return sites


def fake_docker(tmp_path, monkeypatch):
    log = tmp_path / "docker.log"
    exe = tmp_path / "bin" / "docker"
    exe.parent.mkdir()
    exe.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\necho fake docker $1\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{exe.parent}:{os.environ['PATH']}")
    return log


def make_repo(tmp_path, files):
    repo = tmp_path / "remote" / "site"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "first")
    return repo


def run_job(tmp_path, monkeypatch, repo):
    monkeypatch.setattr(deployer, "base_env", lambda: {
        "PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.file://{repo.parent}/.insteadOf", "GIT_CONFIG_VALUE_0": "https://git.test/"})
    for job in sorted((dx.deploy_dir() / "jobs").glob("*.json")):
        deployer.process(job)


BODY = {"name": "Müller Bakery", "repo_url": "https://git.test/site", "branch": "main", "env": []}


def test_create_and_validation(admin, sites_env):
    h = csrf_headers(admin)
    customer = admin.post("/api/customers", json={"name": "Müller"}, headers=h).json()
    r = admin.post("/api/sites", json={**BODY, "customer_id": customer["id"], "token": "glpat-secret-token",
                                       "env": [{"key": "API_KEY", "value": "hunter2hunter2"}]}, headers=h)
    assert r.status_code == 201, r.text
    site = r.json()
    assert site["slug"] == "m-ller-bakery" and site["has_token"] and site["env_keys"] == ["API_KEY"]
    assert "glpat" not in r.text and "hunter2" not in r.text
    # a service of the customer was created
    svc = [s for s in admin.get("/api/services").json() if s["id"] == site["service_id"]][0]
    assert svc["customer_id"] == customer["id"] and svc["folder"] == str(sites_env / "m-ller-bakery")
    # update keeps secrets that were not sent again
    r = admin.put(f"/api/sites/{site['id']}", json={**BODY, "name": "Bakery", "customer_id": customer["id"],
                                                    "env": [{"key": "API_KEY"}]}, headers=h)
    assert r.status_code == 200 and r.json()["has_token"] and r.json()["env_keys"] == ["API_KEY"]
    for bad in ({"repo_url": "https://user:pw@git.test/site"}, {"repo_url": "ext::sh -c id"},
                {"repo_url": "git@git.test:x/y.git"}, {"branch": "--upload-pack=x"}, {"compose_file": "../x.yml"},
                {"env": [{"key": "A B", "value": "x"}]}):
        assert admin.post("/api/sites", json={**BODY, **bad}, headers=h).status_code == 422, bad
    assert admin.post("/api/sites", json={**BODY, "env": [{"key": "NEW"}]}, headers=h).status_code == 422


def test_deploy_needs_running_deployer(admin, sites_env):
    h = csrf_headers(admin)
    site = admin.post("/api/sites", json=BODY, headers=h).json()
    (dx.deploy_dir() / "alive").unlink()
    r = admin.post(f"/api/sites/{site['id']}/deploy", headers=h)
    assert r.status_code == 503 and "deployer" in r.json()["detail"]
    assert admin.get("/api/sites").json()["deployer"] is False


def test_compose_site_end_to_end(admin, sites_env, tmp_path, monkeypatch):
    h = csrf_headers(admin)
    docker_log = fake_docker(tmp_path, monkeypatch)
    repo = make_repo(tmp_path, {"docker-compose.yml": "services:\n  web:\n    image: nginx\n"})
    site = admin.post("/api/sites", json={**BODY, "env": [{"key": "DB_PASSWORD", "value": "s3cret pass"}]},
                      headers=h).json()
    assert admin.post(f"/api/sites/{site['id']}/deploy", headers=h).status_code == 200
    assert admin.get("/api/sites").json()["sites"][0]["status"]["state"] == "queued"
    assert admin.post(f"/api/sites/{site['id']}/deploy", headers=h).status_code == 409  # already queued

    run_job(tmp_path, monkeypatch, repo)
    assert not list((dx.deploy_dir() / "jobs").glob("*.json"))  # job (with secrets) is gone
    status = admin.get(f"/api/sites/{site['id']}").json()["status"]
    assert status["state"] == "ok" and status["commit"] and status["subject"] == "first", status
    assert "s3cret pass" not in status["log"]
    folder = sites_env / site["slug"]
    assert (folder / "docker-compose.yml").is_file()
    env = folder / ".env"
    assert env.read_text() == "DB_PASSWORD='s3cret pass'\n" and stat.S_IMODE(env.stat().st_mode) == 0o600
    called = docker_log.read_text()
    assert f"compose -p site-{site['slug']}" in called and "up -d --build --remove-orphans" in called

    # a new commit is picked up
    (repo / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx:alpine\n")
    git(repo, "commit", "-am", "second")
    assert admin.post(f"/api/sites/{site['id']}/deploy", headers=h).status_code == 200
    run_job(tmp_path, monkeypatch, repo)
    assert admin.get(f"/api/sites/{site['id']}").json()["status"]["subject"] == "second"

    # stop, then remove with files
    admin.post(f"/api/sites/{site['id']}/stop", headers=h)
    run_job(tmp_path, monkeypatch, repo)
    assert " stop" in docker_log.read_text()
    assert admin.delete(f"/api/sites/{site['id']}?purge=true", headers=h).status_code == 204
    run_job(tmp_path, monkeypatch, repo)
    assert not folder.exists() and " down --remove-orphans" in docker_log.read_text()
    actions = [a["action"] for a in admin.get("/api/audit").json()]
    assert "site.deploy" in actions and "site.deleted" in actions


def test_static_site(admin, sites_env, tmp_path, monkeypatch):
    h = csrf_headers(admin)
    fake_docker(tmp_path, monkeypatch)
    repo = make_repo(tmp_path, {"dist/index.html": "<h1>hi</h1>"})
    site = admin.post("/api/sites", json={**BODY, "port": 9123}, headers=h).json()
    admin.post(f"/api/sites/{site['id']}/deploy", headers=h)
    run_job(tmp_path, monkeypatch, repo)
    assert admin.get(f"/api/sites/{site['id']}").json()["status"]["state"] == "ok"
    compose = (sites_env / site["slug"] / deployer.STATIC_COMPOSE).read_text()
    assert '"127.0.0.1:9123:80"' in compose and "./dist:/usr/share/nginx/html:ro" in compose
    assert "return 404" in (sites_env / site["slug"] / deployer.STATIC_NGINX).read_text()


def test_nothing_to_deploy_fails_clearly(admin, sites_env, tmp_path, monkeypatch):
    h = csrf_headers(admin)
    fake_docker(tmp_path, monkeypatch)
    repo = make_repo(tmp_path, {"README.md": "x"})
    site = admin.post("/api/sites", json=BODY, headers=h).json()
    admin.post(f"/api/sites/{site['id']}/deploy", headers=h)
    run_job(tmp_path, monkeypatch, repo)
    status = admin.get(f"/api/sites/{site['id']}").json()["status"]
    assert status["state"] == "failed" and "enter a port" in status["log"]


def test_deployer_rejects_bad_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("XT_SITES_DIR", str(tmp_path / "sites"))
    config.get_settings.cache_clear()
    ok = {"action": "deploy", "slug": "my-site", "repo_url": "https://git.test/a/b", "branch": "main"}
    deployer.validate(ok)
    for bad in ({"slug": "../etc"}, {"slug": "A_b"}, {"action": "rm"}, {"repo_url": "file:///etc"},
                {"repo_url": "https://x.test/a b"}, {"branch": "-x"}, {"compose_file": "a/../../b"},
                {"env": {"A-B": "x"}}, {"port": 0}):
        with pytest.raises(deployer.JobError):
            deployer.validate({**ok, **bad})
    header = deployer.git_env("tok")["GIT_CONFIG_VALUE_0"]
    assert header.startswith("Authorization: Basic ") and "tok" not in header


def test_viewer_cannot_deploy(admin, sites_env):
    h = csrf_headers(admin)
    site = admin.post("/api/sites", json=BODY, headers=h).json()
    admin.post("/api/users", json={"username": "view", "password": "correct horse battery", "role": "viewer"}, headers=h)
    admin.post("/api/auth/logout", headers=h)
    admin.post("/api/auth/login", json={"username": "view", "password": "correct horse battery"})
    h = csrf_headers(admin)
    assert admin.get("/api/sites").status_code == 200
    assert admin.post(f"/api/sites/{site['id']}/deploy", headers=h).status_code == 403
    assert admin.get(f"/api/sites/{site['id']}").status_code == 403
