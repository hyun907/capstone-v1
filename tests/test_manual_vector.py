"""로컬 벡터 인덱스의 갱신과 오류 경계를 합성 runbook으로 검증합니다."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-server"))

import manual_vector


class FakeEmbedding:
    def __init__(self):
        self.embed_calls = 0

    def embed(self, passages):
        self.embed_calls += 1
        return ([1.0, 0.0] if "recovery" in passage else [0.0, 1.0] for passage in passages)

    def query_embed(self, query):
        return iter(([1.0, 0.0],))


class ManualVectorTests(unittest.TestCase):
    def test_missing_data_returns_empty_without_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(manual_vector, "_load_model", side_effect=AssertionError("model loaded")):
                self.assertEqual(manual_vector.search_vector_manual("recovery", 3, Path(directory)), [])

    def test_index_is_reused_then_rebuilt_when_document_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            runbooks = data_dir / "runbooks"
            runbooks.mkdir()
            document = runbooks / "sample.md"
            document.write_text("# Recovery\nrecovery procedure", encoding="utf-8")
            model = FakeEmbedding()
            with patch.object(manual_vector, "_load_model", return_value=model):
                first = manual_vector.search_vector_manual("recovery", 3, data_dir)
                self.assertEqual([item.title for item in first], ["sample"])
                self.assertEqual(first[0].source, "runbook://incident-response/sample")
                self.assertEqual(model.embed_calls, 1)
                manual_vector.search_vector_manual("recovery", 3, data_dir)
                self.assertEqual(model.embed_calls, 1)
                document.write_text("# Other\nunrelated procedure", encoding="utf-8")
                self.assertEqual(manual_vector.search_vector_manual("recovery", 3, data_dir), [])
                self.assertEqual(model.embed_calls, 2)

    def test_invalid_embedding_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            runbooks = data_dir / "runbooks"
            runbooks.mkdir()
            (runbooks / "sample.md").write_text("# Recovery\nrecovery procedure", encoding="utf-8")
            model = FakeEmbedding()
            model.embed = lambda passages: iter(([1.0],))
            with patch.object(manual_vector, "_load_model", return_value=model):
                with self.assertRaisesRegex(RuntimeError, "인덱스 형식"):
                    manual_vector.search_vector_manual("recovery", 3, data_dir)


if __name__ == "__main__":
    unittest.main()
