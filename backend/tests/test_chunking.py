import unittest
from app.rag.chunking import _is_heading, _split_long, chunk_document
from app.rag.metadata import catalog_by_doc_id


class ChunkingTests(unittest.TestCase):
    def document(self, pages):
        return {**next(iter(catalog_by_doc_id().values())), 'pages': pages}

    def test_prose_is_not_heading(self):
        for line in ['this is ordinary prose without punctuation', 'This is ordinary prose without punctuation']:
            self.assertFalse(_is_heading(line))
        for line in ['TREATMENT RECOMMENDATIONS', 'Chapter 2 Treatment', '2.1 Treatment', 'Treatment Options']:
            self.assertTrue(_is_heading(line))

    def test_no_cross_page_text_or_overlap(self):
        chunks=chunk_document(self.document([{'page':9,'text':'first page evidence.'}, {'page':19,'text':'second page evidence.'}]))
        self.assertEqual([(c['page'],c['text']) for c in chunks],[(9,'first page evidence.'),(19,'second page evidence.')])

    def test_section_assignment_and_newlines(self):
        chunks=chunk_document(self.document([{'page':1,'text':'introductory evidence.\nTreatment Options\nbody evidence.\nMonitoring Schedule\nfollow-up evidence.'}]))
        self.assertEqual([c['section'] for c in chunks],['Introduction','Treatment Options','Monitoring Schedule'])
        self.assertEqual(chunks[1]['text'],'Treatment Options\nbody evidence.')

    def test_overlap_and_coverage(self):
        text='0123456789'*10
        chunks=_split_long(text,30,5)
        self.assertTrue(all(len(c)<=30 for c in chunks))
        for left,right in zip(chunks,chunks[1:]):
            self.assertEqual(left[-5:],right[:5])
        self.assertEqual(chunks[0]+''.join(c[5:] for c in chunks[1:]),text)
        self.assertEqual(''.join(_split_long(text,30,0)),text)

    def test_invalid_settings(self):
        for size,overlap in [(0,0),(10,10),(10,-1)]:
            with self.assertRaises(ValueError): _split_long('short',size,overlap)

    def test_empty_pages_and_unique_ids(self):
        chunks=chunk_document(self.document([{'page':1,'text':''},{'page':2,'text':'a'*100}]),30,5)
        self.assertTrue(all(c['page']==2 for c in chunks))
        self.assertEqual(len({c['chunk_id'] for c in chunks}),len(chunks))
