"""Verify the gold annotations against the actual shipped PDFs, without API calls."""
import hashlib
import json
from pathlib import Path
import unicodedata
import unittest

import pymupdf
from app.rag.metadata import catalog_by_doc_id

ROOT = Path(__file__).resolve().parents[2]


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / 'evals/ncd_gold_set.json').read_text())
        cls.catalog = catalog_by_doc_id()

    def test_source_fingerprints(self):
        docs = self.payload['annotation_metadata']['documents']
        self.assertEqual(set(docs), set(self.catalog))
        for doc_id, meta in docs.items():
            with self.subTest(doc_id=doc_id):
                self.assertEqual(meta['filename'], self.catalog[doc_id]['filename'])
                self.assertEqual(hashlib.sha256((ROOT/'data'/meta['filename']).read_bytes()).hexdigest(),meta['sha256'])

    def test_all_answerable_cases_have_verified_page_evidence(self):
        cases = self.payload['cases']
        self.assertEqual(len({c['id'] for c in cases}), len(cases))
        for case in cases:
            with self.subTest(case=case['id']):
                sources = case.get('expected_sources', [])
                if case.get('unanswerable'):
                    self.assertFalse(sources)
                    self.assertFalse(case['expected_doc_ids'])
                    continue
                self.assertTrue(sources)
                self.assertEqual({s['doc_id'] for s in sources},set(case['expected_doc_ids']))
                self.assertEqual(len({(s['doc_id'],s['page']) for s in sources}),len(sources))
                for source in sources:
                    self.assertTrue(source['evidence_excerpt'].strip())
                    with pymupdf.open(ROOT/'data'/self.catalog[source['doc_id']]['filename']) as doc:
                        self.assertTrue(1 <= source['page'] <= len(doc))
                        self.assertIn(normalize(source['evidence_excerpt']),normalize(doc[source['page']-1].get_text()))
