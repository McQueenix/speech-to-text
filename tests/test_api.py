"""CRUD API tests."""


def _create(client, title="Standup", text="Kal meeting hai, please send the report."):
    res = client.post("/api/transcriptions", json={"title": title, "text": text, "language": "auto"})
    assert res.status_code == 201, res.text
    return res.json()


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_create_and_read(client):
    created = _create(client)
    assert created["source"] == "manual"
    res = client.get(f"/api/transcriptions/{created['id']}")
    assert res.status_code == 200
    assert res.json()["text"] == "Kal meeting hai, please send the report."


def test_hindi_text_round_trips(client):
    created = _create(client, title="हिंदी", text="मैं ठीक हूँ, thank you so much!")
    assert client.get(f"/api/transcriptions/{created['id']}").json()["text"] == "मैं ठीक हूँ, thank you so much!"


def test_list_search_and_pagination(client):
    for i in range(12):
        _create(client, title=f"Note {i}", text=f"entry number {i}")
    _create(client, title="Groceries", text="doodh aur bread lana hai")

    page = client.get("/api/transcriptions?limit=5").json()
    assert page["total"] == 13 and len(page["items"]) == 5
    assert page["items"][0]["title"] == "Groceries"  # newest first

    found = client.get("/api/transcriptions?q=doodh").json()
    assert found["total"] == 1 and found["items"][0]["title"] == "Groceries"


def test_update(client):
    created = _create(client)
    res = client.put(f"/api/transcriptions/{created['id']}", json={"text": "Updated text"})
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "Updated text" and body["title"] == "Standup"


def test_delete(client):
    created = _create(client)
    assert client.delete(f"/api/transcriptions/{created['id']}").status_code == 204
    assert client.get(f"/api/transcriptions/{created['id']}").status_code == 404


def test_validation_and_404(client):
    assert client.post("/api/transcriptions", json={"title": "", "text": "x"}).status_code == 422
    assert client.put("/api/transcriptions/999", json={"text": "x"}).status_code == 404
    assert client.delete("/api/transcriptions/999").status_code == 404
