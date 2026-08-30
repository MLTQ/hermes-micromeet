"""Tests for verified notice hydration and attachment projection."""

from __future__ import annotations

import unittest

from bootstrap import load_module

messages = load_module("messages")


class FakeClient:
    def __init__(self, post: dict) -> None:
        self.post = post

    def run(self, _command):
        return {
            "ok": True,
            "result": {
                "summary": {"topic_id": "b" * 64, "title": "Coordinate parser fix"},
                "posts": [self.post],
            },
        }


def notice() -> dict:
    return {
        "cursor": 9,
        "object_id": "a" * 64,
        "kind": "post",
        "thread_id": "c" * 64,
        "author": {"id": "ed25519:" + "d" * 64},
    }


def post() -> dict:
    return {
        "id": "a" * 64,
        "author": {
            "id": "ed25519:" + "d" * 64,
            "signature_valid": True,
            "label": "peer",
        },
        "body": "Reproduced on arm64.",
        "attachments": [],
        "created_at": "2026-08-30T01:00:00Z",
        "content_trust": "untrusted_remote",
    }


class MessageTests(unittest.TestCase):
    def test_projects_verified_post(self) -> None:
        projected = messages.project_notice(FakeClient(post()), notice())
        self.assertIsNotNone(projected)
        self.assertEqual(projected.author_name, "peer")
        self.assertEqual(projected.thread_id, "c" * 64)
        self.assertEqual(projected.content_trust, "untrusted_remote")

    def test_attachment_is_metadata_not_a_local_path(self) -> None:
        value = post()
        value["attachments"] = [
            {"name": "trace.txt", "size": 12, "hash": "e" * 64, "ticket": "blob-ticket"}
        ]
        projected = messages.project_notice(FakeClient(value), notice())
        self.assertIn("nothing was downloaded automatically", projected.body)
        self.assertIn("blob-ticket", projected.body)

    def test_rejects_invalid_signature_verdict(self) -> None:
        value = post()
        value["author"]["signature_valid"] = False
        with self.assertRaises(messages.ProjectionError):
            messages.project_notice(FakeClient(value), notice())

    def test_classifies_post_outside_bounded_history(self) -> None:
        client = FakeClient(post())
        client.post["id"] = "f" * 64
        with self.assertRaises(messages.HistoryWindowMiss):
            messages.project_notice(client, notice())


if __name__ == "__main__":
    unittest.main()
