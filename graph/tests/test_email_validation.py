import unittest
from unittest.mock import patch
import requests

from graph.nodes.fetch_order import fetch_order_node
from graph.nodes.email_mismatch import email_mismatch_node
from graph.builder import route_after_fetch_order


class TestEmailValidation(unittest.TestCase):
    """Test cases for email validation logic"""

    @patch('graph.nodes.fetch_order.requests.get')
    def test_email_match(self, mock_get):
        """Test when extracted email matches order email"""
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "order_id": "ORD1002",
            "customer_email": "alice@example.com",
            "product": "Speaker"
        }

        state = {
            "order_id": "ORD1002",
            "customer_email": "alice@example.com",
            "messages": [],
            "evidence": None
        }

        result = fetch_order_node(state)

        self.assertEqual(result["email_mismatch"], False)
        self.assertIn("Email validation successful", result["messages"][-1]["content"])

    @patch('graph.nodes.fetch_order.requests.get')
    def test_email_mismatch(self, mock_get):
        """Test when extracted email does not match order email"""
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "order_id": "ORD1002",
            "customer_email": "bob@example.com",
            "product": "Speaker"
        }

        state = {
            "order_id": "ORD1002",
            "customer_email": "alice@example.com",
            "messages": [],
            "evidence": None
        }

        result = fetch_order_node(state)

        self.assertEqual(result["email_mismatch"], True)
        self.assertIn("Email mismatch detected", result["messages"][-1]["content"])

    @patch('graph.nodes.fetch_order.requests.get')
    def test_no_email_extracted(self, mock_get):
        """Test when no email was extracted from ticket"""
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "order_id": "ORD1002",
            "customer_email": "alice@example.com",
            "product": "Speaker"
        }

        state = {
            "order_id": "ORD1002",
            "customer_email": None,
            "messages": [],
            "evidence": None
        }

        result = fetch_order_node(state)

        # Should not set email_mismatch when no email extracted
        self.assertNotIn("email_mismatch", result)

    def test_route_after_fetch_order_mismatch(self):
        """Test routing when email mismatch occurs"""
        state = {"email_mismatch": True}
        result = route_after_fetch_order(state)
        self.assertEqual(result, "email_mismatch")

    def test_route_after_fetch_order_match(self):
        """Test routing when email matches"""
        state = {"email_mismatch": False}
        result = route_after_fetch_order(state)
        self.assertEqual(result, "classify")

    def test_email_mismatch_node(self):
        """Test email_mismatch node sets correct recommendation"""
        state = {
            "customer_email": "alice@example.com",
            "evidence": {"customer_email": "bob@example.com"},
            "messages": [],
            "recommendation": None
        }

        result = email_mismatch_node(state)

        self.assertIsNotNone(result["recommendation"])
        self.assertIn("do not match", result["recommendation"])
        self.assertIn("alice@example.com", result["recommendation"])
        self.assertIn("bob@example.com", result["recommendation"])


if __name__ == "__main__":
    unittest.main()
