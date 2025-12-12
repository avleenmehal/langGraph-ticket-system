import unittest
from unittest.mock import patch, Mock
import requests
from graph.nodes.draft_reply import draft_reply_node
from graph.TriageState import TriageState


class TestDraftReplyNode(unittest.TestCase):
    """Test cases for the draft_reply_node function"""

    def setUp(self):
        """Set up test state before each test"""
        self.base_state = {
            "ticket_text": "My speaker is not working ORD1002",
            "order_id": "ORD1002",
            "customer_email": None,
            "messages": [{"role": "user", "content": "My speaker is not working ORD1002"}],
            "issue_type": "defective",
            "evidence": {
                "order_id": "ORD1002",
                "customer_name": "Alice",
                "email": "alice@example.com",
                "product": "Bluetooth Speaker"
            },
            "recommendation": None
        }

    @patch('graph.nodes.draft_reply.requests.post')
    def test_draft_reply_success(self, mock_post):
        """Test successful reply generation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reply_text": "Hi Alice, we are processing a replacement for your Bluetooth Speaker (ORD1002)."
        }
        mock_post.return_value = mock_response

        result = draft_reply_node(self.base_state.copy())

        self.assertIsNotNone(result["recommendation"])
        self.assertIn("Alice", result["recommendation"])
        self.assertIn("ORD1002", result["recommendation"])
        self.assertIn("Generated reply recommendation", result["messages"][1]["content"])

    @patch('graph.nodes.draft_reply.requests.post')
    def test_draft_reply_shipping_issue(self, mock_post):
        """Test reply for shipping issue"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reply_text": "Hi Alice, we are checking on the shipping status for ORD1002."
        }
        mock_post.return_value = mock_response

        state = self.base_state.copy()
        state["issue_type"] = "shipping"

        result = draft_reply_node(state)

        self.assertIn("shipping", result["recommendation"])

    @patch('graph.nodes.draft_reply.requests.post')
    def test_draft_reply_network_error(self, mock_post):
        """Test handling of network errors"""
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        result = draft_reply_node(self.base_state.copy())

        self.assertEqual(result["recommendation"], "Unable to generate response at this time.")
        self.assertIn("Failed to generate reply", result["messages"][1]["content"])

    @patch('graph.nodes.draft_reply.requests.post')
    def test_draft_reply_http_error(self, mock_post):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Server error")
        mock_post.return_value = mock_response

        result = draft_reply_node(self.base_state.copy())

        self.assertEqual(result["recommendation"], "Unable to generate response at this time.")

if __name__ == "__main__":
    unittest.main()
