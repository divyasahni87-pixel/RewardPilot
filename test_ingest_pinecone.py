"""Offline ingestion tests; no remote writes."""

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import ingest_pinecone as ingestion


class IngestionTests(unittest.TestCase):
    def test_complete_document_stable_id_and_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            text = (ingestion.RAG_DIR / "amex_delta_transfer_policy.md").read_text(encoding="utf-8")
            (root / "amex_delta_transfer_policy.md").write_text(text, encoding="utf-8")
            (root / "README.md").write_text("Skip this")
            with patch.object(ingestion, "get_embedding", return_value=[0.0] * ingestion.DIMENSION) as embed:
                vectors = ingestion.prepare_vectors(root)
            embed.assert_called_once_with(text)
            self.assertEqual(len(vectors), 1)
            self.assertEqual(vectors[0]["id"], "amex_delta_transfer_policy")
            metadata = vectors[0]["metadata"]
            self.assertEqual(metadata["text"], text)
            for key in ("title", "program", "source_url", "last_verified", "source_file",
                        "document_type", "policy_type", "tags"):
                self.assertIn(key, metadata)
            self.assertIsInstance(metadata["tags"], list)

    def test_replacement_clears_only_policy_namespace_before_upsert(self):
        index = Mock()
        vectors = [{"id": "policy"}]
        with patch.object(ingestion, "wait_for_vectors", return_value=1) as wait:
            self.assertEqual(ingestion.replace_policy_vectors(index, vectors), 1)
        self.assertEqual([call[0] for call in index.mock_calls], ["delete", "upsert"])
        index.delete.assert_called_once_with(delete_all=True, namespace=ingestion.NAMESPACE)
        self.assertEqual(wait.call_args_list[0].args, (index, set()))
        self.assertEqual(wait.call_args_list[1].args, (index, {"policy"}))

    def test_empty_corpus_cannot_clear_namespace(self):
        index = Mock()
        with self.assertRaises(ValueError):
            ingestion.replace_policy_vectors(index, [])
        index.delete.assert_not_called()

    def test_verification_accepts_sdk_list_items(self):
        index = Mock()
        index.list.return_value = [[SimpleNamespace(id="policy")]]
        index.describe_index_stats.return_value.namespaces = {
            ingestion.NAMESPACE: SimpleNamespace(vector_count=1)}
        self.assertEqual(ingestion.wait_for_vectors(index, {"policy"}), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
