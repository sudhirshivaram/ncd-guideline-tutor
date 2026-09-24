import json
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rank_bm25 import BM25Okapi
from app.rag import indexing, retrieve


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.chunk = {key: 'sample' for key in ('chunk_id', 'text', 'doc_id', 'filename', 'title', 'short_title', 'publisher', 'doc_type', 'ncd_types', 'audience', 'source_family', 'section')}
        self.chunk.update(page=1, year=2021)
        (self.root/'chunks.jsonl').write_text(json.dumps(self.chunk)+'\n')
        with (self.root/'bm25.pkl').open('wb') as f:
            pickle.dump({'bm25': BM25Okapi([['sample']]), 'ids': ['sample']}, f)
        (self.root/'chroma').mkdir()
        (self.root/'chroma/chroma.sqlite3').write_bytes(b'fixture')
        self.client = MagicMock()
        self.client.get_collection.return_value.get.return_value = {'ids': ['sample']}
        self.patch = patch.object(indexing.chromadb, 'PersistentClient', return_value=self.client)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_valid(self):
        self.assertTrue(indexing.index_is_ready(self.root))

    def test_missing_components(self):
        for relative in ['chunks.jsonl', 'bm25.pkl', 'chroma/chroma.sqlite3']:
            with self.subTest(relative=relative):
                p=self.root/relative
                content=p.read_bytes(); p.unlink()
                self.assertFalse(indexing.index_is_ready(self.root))
                p.write_bytes(content)

    def test_corrupt_pickle(self):
        (self.root/'bm25.pkl').write_bytes(b'broken')
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_empty_chunks(self):
        (self.root/'chunks.jsonl').write_text('')
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_wrong_bm25_ids(self):
        with (self.root/'bm25.pkl').open('wb') as f:
            pickle.dump({'bm25': BM25Okapi([['sample']]), 'ids': ['other']}, f)
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_vector_ids_mismatch(self):
        self.client.get_collection.return_value.get.return_value={'ids':['other']}
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_missing_collection(self):
        self.client.get_collection.side_effect=RuntimeError('missing')
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_interrupted_build(self):
        (self.root/indexing.BUILD_MARKER).touch()
        self.assertFalse(indexing.index_is_ready(self.root))

    def test_failed_build_stays_unready(self):
        with patch.object(indexing,'ingest_corpus',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                indexing.build_index(index_dir=self.root)
        self.assertTrue((self.root/indexing.BUILD_MARKER).exists())
        self.assertFalse(indexing.index_is_ready(self.root))


class RetrievalTests(unittest.TestCase):
    def test_vector_failure_does_not_fall_back_to_keywords(self):
        store=MagicMock(); store.collection.query.side_effect=RuntimeError('database down')
        with patch.object(retrieve,'get_store',return_value=store), patch.object(retrieve,'embed_query',return_value=[1.0]), patch.object(retrieve,'_bm25_search') as bm25:
            with self.assertRaises(retrieve.RetrievalError): retrieve.retrieve('question')
            bm25.assert_not_called()

    def test_empty_result_is_not_an_error(self):
        store=MagicMock(); store.collection.query.return_value={'ids':[[]]}
        with patch.object(retrieve,'get_store',return_value=store), patch.object(retrieve,'embed_query',return_value=[1.0]):
            self.assertEqual(retrieve.retrieve('question',hybrid=False),[])

    def test_keyword_failure(self):
        with patch.object(retrieve,'get_store'), patch.object(retrieve,'_vector_search',return_value=[]), patch.object(retrieve,'_bm25_search',side_effect=RuntimeError('broken')):
            with self.assertRaises(retrieve.RetrievalError): retrieve.retrieve('question')

    def test_embedding_failure(self):
        with patch.object(retrieve,'get_store'), patch.object(retrieve,'embed_query',side_effect=RuntimeError('model failed')):
            with self.assertRaises(retrieve.RetrievalError): retrieve.retrieve('question')


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.main import app
        from fastapi.testclient import TestClient
        cls.client=TestClient(app)

    def test_unready_health_is_503(self):
        with patch('app.main.index_is_ready',return_value=False):
            response=self.client.get('/api/health')
        self.assertEqual(response.status_code,503)
        self.assertFalse(response.json()['index_ready'])

    def test_chat_stream_surfaces_error(self):
        async def failure(**kwargs):
            raise retrieve.RetrievalError('Semantic search failed.')
            yield
        with patch('app.api.routes.chat.index_is_ready',return_value=True), patch('app.api.routes.chat.stream_answer',failure):
            response=self.client.post('/api/chat',json={'message':'question'},headers={'X-API-Key':'test-only'})
        self.assertIn('"type": "error"',response.text)
        self.assertIn('Semantic search failed.',response.text)
        self.assertNotIn('"type": "token"',response.text)


class StartupTests(unittest.TestCase):
    def test_startup_rebuild_and_failure_paths(self):
        import os
        import subprocess
        script = Path(__file__).resolve().parents[1] / 'entrypoint.sh'
        for scenario in ['ready', 'incomplete', 'build_failed', 'still_invalid']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                python=root/'python'
                python.write_text('''#!/bin/bash
if [[ "$*" == *--check* ]]; then
  echo check >> "$TEST_LOG"
  if [ "$SCENARIO" = ready ]; then exit 0; fi
  if [ "$SCENARIO" = incomplete ] && [ -f "$TEST_DONE" ]; then exit 0; fi
  exit 1
fi
echo build >> "$TEST_LOG"
if [ "$SCENARIO" = build_failed ]; then exit 1; fi
touch "$TEST_DONE"
''')
                uvicorn=root/'uvicorn'
                uvicorn.write_text('#!/bin/bash\necho serve >> "$TEST_LOG"\n')
                python.chmod(0o755); uvicorn.chmod(0o755)
                env=dict(os.environ, PATH=str(root)+':'+os.environ['PATH'], SCENARIO=scenario, TEST_LOG=str(root/'log'), TEST_DONE=str(root/'done'))
                result=subprocess.run(['bash',str(script)],env=env,capture_output=True,text=True)
                events=(root/'log').read_text().splitlines()
                if scenario in ['ready','incomplete']:
                    self.assertEqual(result.returncode,0)
                    self.assertEqual(events, ['check','check','serve'] if scenario=='ready' else ['check','build','check','serve'])
                else:
                    self.assertNotEqual(result.returncode,0)
                    self.assertNotIn('serve',events)
