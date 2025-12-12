import unittest
from unittest.mock import patch, Mock
import requests
from graph.nodes.fetch_order import fetch_order_node, fetch_order_tool
from graph.TriageState import TriageState


class TestFetchOrderTool(unittest.TestCase):
    """Test cases for the fetch_order_tool"""

    @patch('graph.nodes.fetch_order.requests.get')
    def test_tool_success(self, mock_get):
        """Test successful order fetch via tool"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "order_id": "ORD1002",
            "customer_name": "Alice",
            "email": "alice@example.com"
        }
        mock_get.return_value = mock_response

        result = fetch_order_tool.invoke({"order_id": "ORD1002"})

        self.assertEqual(result["order_id"], "ORD1002")
        self.assertEqual(result["customer_name"], "Alice")
        self.assertNotIn("error", result)

    @patch('graph.nodes.fetch_order.requests.get')
    def test_tool_order_not_found(self, mock_get):
        """Test tool behavior when order is not found"""
        mock_response = Mock()
        mock_response.status_code = 404

        # Create HTTPError with response attribute
        http_error = requests.exceptions.HTTPError("Not found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        result = fetch_order_tool.invoke({"order_id": "ORD9999"})

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Order not found")

    @patch('graph.nodes.fetch_order.requests.get')
    def test_tool_network_error(self, mock_get):
        """Test tool behavior on network error"""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = fetch_order_tool.invoke({"order_id": "ORD1002"})

        self.assertIn("error", result)
        self.assertIn("Request failed", result["error"])


class TestFetchOrderNode(unittest.TestCase):
    """Test cases for the fetch_order_node function"""

    def setUp(self):
        """Set up test state before each test"""
        self.base_state = {
            "ticket_text": "My speaker is not working ORD1002",
            "order_id": "ORD1002",
            "customer_email": None,
            "messages": [{"role": "user", "content": "My speaker is not working ORD1002"}],
            "issue_type": "defective",
            "evidence": None,
            "recommendation": None
        }

    @patch('graph.nodes.fetch_order.requests.get')
    def test_fetch_order_success(self, mock_get):
        """Test successful order fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "order_id": "ORD1002",
            "customer_name": "Alice",
            "email": "alice@example.com",
            "product": "Bluetooth Speaker"
        }
        mock_get.return_value = mock_response

        result = fetch_order_node(self.base_state.copy())

        self.assertIsNotNone(result["evidence"])
        self.assertEqual(result["evidence"]["order_id"], "ORD1002")
        self.assertEqual(result["evidence"]["customer_name"], "Alice")
        self.assertIn("Fetched order details: ORD1002", result["messages"][1]["content"])

    @patch('graph.nodes.fetch_order.requests.get')
    def test_fetch_order_not_found(self, mock_get):
        """Test when order is not found"""
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = requests.exceptions.HTTPError("Not found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response

        result = fetch_order_node(self.base_state.copy())

        self.assertIn("error", result["evidence"])
        self.assertIn("Error:", result["messages"][1]["content"])

    def test_fetch_order_no_order_id(self):
        """Test when no order_id is in state"""
        state = self.base_state.copy()
        state["order_id"] = None

        result = fetch_order_node(state)

        self.assertIsNone(result["evidence"])
        self.assertIn("Skipped order fetch", result["messages"][1]["content"])

    def test_fetch_order_empty_order_id(self):
        """Test with empty string order_id"""
        state = self.base_state.copy()
        state["order_id"] = ""

        result = fetch_order_node(state)

        self.assertIn("Skipped order fetch", result["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
