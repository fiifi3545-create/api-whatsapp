def test_verify_returns_challenge_for_matching_token(client):
    resp = client.get(
        "/webhooks/whatsapp",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-token",
            "hub.challenge": "abc123",
        },
    )
    assert resp.status_code == 200
    assert resp.data == b"abc123"


def test_verify_rejects_wrong_token(client):
    resp = client.get(
        "/webhooks/whatsapp",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "abc123",
        },
    )
    assert resp.status_code == 403


def test_inbound_text_message_dispatches(client):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "233200000001",
                                    "id": "wamid.TEST",
                                    "type": "text",
                                    "text": {"body": "when is the exam"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    resp = client.post("/webhooks/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.get_json() == {"received": 1}


def test_inbound_ignores_unsupported_type(client):
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [{"from": "x", "type": "audio"}]}}]}
        ]
    }
    resp = client.post("/webhooks/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.get_json() == {"received": 0}
