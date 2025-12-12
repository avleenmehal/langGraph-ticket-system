import unittest
from unittest.mock import patch, Mock
import requests
from graph.nodes.search_orders import search_orders_node, search_orders_tool
from graph.TriageState import TriageState


class TestSearchOrdersTool(unittest.TestCase):
    """Test cases for the search_orders_tool"""

    @patch('graph.nodes.search_orders.requests.get')
    def test_tool_search_by_email_success(self, mock_get):
        """Test successful search by email"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"order_id": "ORD1002", "customer_name": "Alice", "email": "alice@example.com"}
            ]
        }
        mock_get.return_value = mock_response

        result = search_orders_tool.invoke({"customer_email": "alice@example.com"})

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["order_id"], "ORD1002")

    @patch('graph.nodes.search_orders.requests.get')
    def test_tool_no_results(self, mock_get):
        """Test when no orders are found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        result = search_orders_tool.invoke({"customer_email": "unknown@example.com"})

        self.assertEqual(len(result["results"]), 0)

    @patch('graph.nodes.search_orders.requests.get')
    def test_tool_network_error(self, mock_get):
        """Test tool behavior on network error"""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = search_orders_tool.invoke({"customer_email": "alice@example.com"})

        self.assertIn("error", result)
        self.assertEqual(result["results"], [])


class TestSearchOrdersNode(unittest.TestCase):
    """Test cases for the search_orders_node function"""

    def setUp(self):
        """Set up test state before each test"""
        self.base_state = {
            "ticket_text": "My product is broken alice@example.com",
            "order_id": None,
            "customer_email": "alice@example.com",
            "messages": [{"role": "user", "content": "My product is broken alice@example.com"}],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

    @patch('graph.nodes.search_orders.requests.get')
    def test_search_single_result(self, mock_get):
        """Test when search finds exactly one order"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"order_id": "ORD1002", "customer_name": "Alice", "email": "alice@example.com"}
            ]
        }
        mock_get.return_value = mock_response

        result = search_orders_node(self.base_state.copy())

        self.assertEqual(result["order_id"], "ORD1002")
        self.assertIsNotNone(result["evidence"])
        self.assertEqual(result["evidence"]["order_id"], "ORD1002")
        self.assertIn("Found order ORD1002", result["messages"][1]["content"])

    @patch('graph.nodes.search_orders.requests.get')
    def test_search_multiple_results(self, mock_get):
        """Test when search finds multiple orders"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"order_id": "ORD1002", "customer_name": "Alice"},
                {"order_id": "ORD1003", "customer_name": "Alice"}
            ]
        }
        mock_get.return_value = mock_response

        result = search_orders_node(self.base_state.copy())

        self.assertIsNone(result["order_id"])
        self.assertIn("multiple_orders", result["evidence"])
        self.assertEqual(result["evidence"]["count"], 2)
        self.assertIn("Found 2 orders", result["messages"][1]["content"])

    @patch('graph.nodes.search_orders.requests.get')
    def test_search_no_results(self, mock_get):
        """Test when search finds no orders"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        result = search_orders_node(self.base_state.copy())

        self.assertIsNone(result["order_id"])
        self.assertIn("No orders found", result["messages"][1]["content"])

    def test_search_no_email(self):
        """Test when no customer_email is in state"""
        state = self.base_state.copy()
        state["customer_email"] = None

        result = search_orders_node(state)

        self.assertIn("No customer email found", result["messages"][1]["content"])

    @patch('graph.nodes.search_orders.requests.get')
    def test_search_error(self, mock_get):
        """Test when search returns an error"""
        mock_get.side_effect = requests.exceptions.RequestException("Search failed")

        result = search_orders_node(self.base_state.copy())

        self.assertIn("Error:", result["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
