import unittest
from unittest.mock import patch, AsyncMock

from app.eval.metrics import citation_metrics, abstention_signal, summarize, document_hit_rate_at_k
from app.eval.runner import run_evaluation


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{'index': 1, 'doc_id': 'a', 'page': 7}, {'index': 2, 'doc_id': 'b', 'page': 7}]
        self.gold = [{'doc_id': 'a', 'page': 7}]

    def test_unannotated_is_unscored(self):
        self.assertIsNone(citation_metrics('Answer [1]', self.sources, [])['citation_source_precision'])
        self.assertEqual(summarize([{'x': None}, {'x': 0.0}], 'x'), {'mean': 0.0, 'n_scored': 1, 'n_total': 2})

    def test_only_used_sources_count(self):
        self.assertEqual(citation_metrics('Answer [2]', self.sources, self.gold)['citation_source_hit'], 0)
        self.assertEqual(citation_metrics('Answer', self.sources, self.gold)['citation_source_precision'], 0)

    def test_wrong_document_same_page_and_invalid_id(self):
        scores = citation_metrics('Answer [1, 2] [99] [1]', self.sources, self.gold)
        self.assertEqual(scores['citation_source_precision'], 0.333)
        self.assertEqual(scores['citation_id_precision'], 0.667)
        self.assertEqual(scores['invalid_citation_ids'], [99])

    def test_correct_document_wrong_page(self):
        self.assertEqual(citation_metrics('Answer [1]', self.sources, [{'doc_id': 'a', 'page': 8}])['citation_source_hit'], 0)

    def test_abstention_signal(self):
        self.assertTrue(abstention_signal('The sources do not contain this information.'))
        self.assertFalse(abstention_signal('Take the following treatment.'))

    def test_hit_rate(self):
        self.assertEqual(document_hit_rate_at_k([1, 6, None], 5), 0.333)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_missing_annotations_and_unanswerable_reporting(self):
        cases = [{'id': 'a', 'question': 'question', 'expected_doc_ids': ['a'], 'filters': {'year': 2021}},
                 {'id': 'b', 'question': 'outside corpus', 'expected_doc_ids': [], 'unanswerable': True}]
        with patch('app.eval.runner.load_gold_set', return_value=cases), patch('app.eval.runner.retrieve_contexts', return_value=[]) as retrieve, patch('app.eval.runner.to_citations', return_value=[]), patch('app.eval.runner._complete_answer', new=AsyncMock(side_effect=['An answer.', 'The sources do not contain this information.'])):
            result = await run_evaluation(include_generation=True, api_key='test-only')
        self.assertEqual(retrieve.call_args_list[1].args[1].filters.year, 2021)
        metrics = result['generation']['metrics']
        self.assertEqual(metrics['citation_source_precision']['n_scored'], 0)
        self.assertIsNone(metrics['citation_source_precision']['mean'])
        self.assertEqual(metrics['unanswerable_abstention_signal']['mean'], 1)
        self.assertEqual(metrics['unanswerable_abstention_signal']['n_scored'], 1)
        self.assertEqual(metrics['answer_context_token_overlap']['n_scored'], 1)
        self.assertEqual(result['retrieval']['n'], 1)
        self.assertEqual(result['schema_version'], 2)

    async def test_invalid_case_limit(self):
        with self.assertRaises(ValueError):
            await run_evaluation(max_cases=0)


if __name__ == '__main__':
    unittest.main()
