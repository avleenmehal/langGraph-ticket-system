import unittest
from unittest.mock import patch, Mock
import requests
from graph.nodes.classify import classify_node
from graph.TriageState import TriageState


class TestClassifyNode(unittest.TestCase):
    """Test cases for the classify_node function"""

    def setUp(self):
        """Set up test state before each test"""
        self.base_state = {
            "ticket_text": "My speaker is not working ORD1002",
            "order_id": "ORD1002",
            "customer_email": None,
            "messages": [{"role": "user", "content": "My speaker is not working ORD1002"}],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

    @patch('graph.nodes.classify.requests.post')
    def test_classify_success(self, mock_post):
        """Test successful classification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issue_type": "defective"}
        mock_post.return_value = mock_response

        result = classify_node(self.base_state.copy())

        self.assertEqual(result["issue_type"], "defective")
        self.assertEqual(len(result["messages"]), 2)
        self.assertIn("Classified as: defective", result["messages"][1]["content"])

    @patch('graph.nodes.classify.requests.post')
    def test_classify_shipping_issue(self, mock_post):
        """Test classification for shipping issue"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issue_type": "shipping"}
        mock_post.return_value = mock_response

        result = classify_node(self.base_state.copy())

        self.assertEqual(result["issue_type"], "shipping")
        self.assertIn("Classified as: shipping", result["messages"][1]["content"])

    @patch('graph.nodes.classify.requests.post')
    def test_classify_refund_issue(self, mock_post):
        """Test classification for refund issue"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issue_type": "refund"}
        mock_post.return_value = mock_response

        result = classify_node(self.base_state.copy())

        self.assertEqual(result["issue_type"], "refund")

    @patch('graph.nodes.classify.requests.post')
    def test_classify_network_error(self, mock_post):
        """Test handling of network errors"""
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        result = classify_node(self.base_state.copy())

        self.assertEqual(result["issue_type"], "unknown")
        self.assertIn("Classification failed", result["messages"][1]["content"])

    @patch('graph.nodes.classify.requests.post')
    def test_classify_http_error(self, mock_post):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Server error")
        mock_post.return_value = mock_response

        result = classify_node(self.base_state.copy())

        self.assertEqual(result["issue_type"], "unknown")

    @patch('graph.nodes.classify.requests.post')
    def test_classify_preserves_other_state(self, mock_post):
        """Test that classification preserves other state fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issue_type": "defective"}
        mock_post.return_value = mock_response

        state = self.base_state.copy()
        state["evidence"] = {"order_id": "ORD1002"}
        state["recommendation"] = "Test recommendation"

        result = classify_node(state)

        self.assertEqual(result["order_id"], "ORD1002")
        self.assertEqual(result["evidence"], {"order_id": "ORD1002"})
        self.assertEqual(result["recommendation"], "Test recommendation")

    @patch('graph.nodes.classify.requests.post')
    def test_classify_calls_correct_endpoint(self, mock_post):
        """Test that the correct API endpoint is called"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issue_type": "defective"}
        mock_post.return_value = mock_response

        classify_node(self.base_state.copy())

        # Verify the endpoint was called with correct payload
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("classify/issue", args[0])
        self.assertEqual(kwargs["json"]["ticket_text"], "My speaker is not working ORD1002")


if __name__ == "__main__":
    unittest.main()
