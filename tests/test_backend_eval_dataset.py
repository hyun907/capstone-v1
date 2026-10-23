"""LangSmith 연결 없이 평가 데이터셋 등록 동작을 확인한다."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.eval.create_dataset import DATASET_NAME, dataset_examples, ensure_dataset, main


class FakeClient:
    def __init__(self) -> None:
        self.dataset = None
        self.examples = []
        self.create_examples_calls = 0

    def has_dataset(self, *, dataset_name: str) -> bool:
        assert dataset_name == DATASET_NAME
        return self.dataset is not None

    def read_dataset(self, *, dataset_name: str) -> SimpleNamespace:
        assert dataset_name == DATASET_NAME
        return self.dataset

    def create_dataset(self, *, dataset_name: str, description: str) -> SimpleNamespace:
        assert dataset_name == DATASET_NAME
        assert description
        self.dataset = SimpleNamespace(id=uuid4())
        return self.dataset

    def list_examples(self, *, dataset_id) -> list[SimpleNamespace]:
        assert dataset_id == self.dataset.id
        return self.examples

    def create_examples(self, *, dataset_id, examples: list[dict]) -> None:
        assert dataset_id == self.dataset.id
        self.create_examples_calls += 1
        self.examples.extend(
            SimpleNamespace(inputs=item["inputs"], outputs=item["outputs"])
            for item in examples
        )


class DatasetTests(unittest.TestCase):
    def test_five_examples_use_supported_read_only_tools(self) -> None:
        examples = dataset_examples()

        self.assertEqual(len(examples), 5)
        self.assertEqual(len({item["inputs"]["message"] for item in examples}), 5)
        supported_tools = {
            "search_operations_manual",
            "get_monitoring_status",
            "search_jira_tickets",
        }
        for item in examples:
            self.assertEqual(set(item), {"inputs", "outputs"})
            self.assertEqual(set(item["inputs"]), {"message"})
            self.assertEqual(
                set(item["outputs"]),
                {"expected_topics", "expected_tools_used", "should_include_steps"},
            )
            self.assertTrue(set(item["outputs"]["expected_tools_used"]) <= supported_tools)
        self.assertFalse(any("네트워크" in item["inputs"]["message"] for item in examples))
        self.assertEqual(examples[-1]["outputs"]["expected_tools_used"], [])

    def test_repeated_execution_does_not_duplicate_examples(self) -> None:
        client = FakeClient()

        dataset_id, created = ensure_dataset(client)
        client.examples.reverse()
        repeated_id, repeated_created = ensure_dataset(client)

        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(dataset_id, repeated_id)
        self.assertEqual(len(client.examples), 5)
        self.assertEqual(client.create_examples_calls, 1)

    def test_conflicting_existing_examples_are_preserved(self) -> None:
        client = FakeClient()
        ensure_dataset(client)
        client.examples[0].outputs["expected_topics"] = ["다른 기대값"]

        with self.assertRaisesRegex(RuntimeError, "기존 예시 5건"):
            ensure_dataset(client)

        self.assertEqual(len(client.examples), 5)
        self.assertEqual(client.create_examples_calls, 1)

    def test_missing_key_does_not_connect(self) -> None:
        with patch.dict(os.environ, {"LANGSMITH_API_KEY": ""}), patch(
            "backend.eval.create_dataset.Client"
        ) as client_class:
            with self.assertRaisesRegex(SystemExit, "LANGSMITH_API_KEY"):
                main()

        client_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
