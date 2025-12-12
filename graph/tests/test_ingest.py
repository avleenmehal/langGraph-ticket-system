import unittest
from graph.nodes.ingest import ingest_node, extract_order_id
from graph.TriageState import TriageState


class TestExtractOrderId(unittest.TestCase):
    """Test cases for the extract_order_id function"""

    def test_extract_ord_format(self):
        """Test extraction of ORD format order IDs"""
        text = "My speaker is not working ORD1002"
        result = extract_order_id(text)
        self.assertEqual(result, "ORD1002")

    def test_extract_ord_format_lowercase(self):
        """Test extraction with lowercase ord"""
        text = "Issue with ord1004"
        result = extract_order_id(text)
        self.assertEqual(result, "ord1004")

    def test_no_order_id_found(self):
        """Test when no order ID is present"""
        text = "My product is broken order23"
        result = extract_order_id(text)
        self.assertIsNone(result)

class TestIngestNode(unittest.TestCase):
    """Test cases for the ingest_node function"""

    def test_ingest_with_order_id_in_text(self):
        """Test ingest when order_id is in ticket text"""
        state = {
            "ticket_text": "My speaker is not working ORD1002",
            "order_id": None,
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        self.assertEqual(result["order_id"], "ORD1002")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][0]["role"], "user")
        self.assertEqual(result["messages"][0]["content"], "My speaker is not working ORD1002")
        self.assertEqual(result["messages"][1]["role"], "assistant")
        self.assertIn("Extracted order_id: ORD1002", result["messages"][1]["content"])

    def test_ingest_with_provided_order_id(self):
        """Test ingest when order_id is already provided"""
        state = {
            "ticket_text": "My product is broken",
            "order_id": "ORD1005",
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        self.assertEqual(result["order_id"], "ORD1005")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][1]["role"], "assistant")
        self.assertIn("Order_id provided: ORD1005", result["messages"][1]["content"])

    def test_ingest_without_order_id(self):
        """Test ingest when no order_id is found"""
        state = {
            "ticket_text": "My product is broken",
            "order_id": None,
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        self.assertIsNone(result["order_id"])
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][1]["role"], "assistant")
        self.assertIn("No order_id found in ticket", result["messages"][1]["content"])

    def test_ingest_preserves_other_state(self):
        """Test that ingest preserves other state fields"""
        state = {
            "ticket_text": "Issue with ORD1002",
            "order_id": None,
            "messages": [],
            "issue_type": "defective",
            "evidence": {"some": "data"},
            "recommendation": "test"
        }

        result = ingest_node(state)

        self.assertEqual(result["issue_type"], "defective")
        self.assertEqual(result["evidence"], {"some": "data"})
        self.assertEqual(result["recommendation"], "test")

    def test_ingest_message_format(self):
        """Test that messages are formatted correctly"""
        state = {
            "ticket_text": "Test ticket ORD1002",
            "order_id": None,
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        # Check user message
        self.assertIsInstance(result["messages"][0], dict)
        self.assertIn("role", result["messages"][0])
        self.assertIn("content", result["messages"][0])

        # Check assistant message
        self.assertIsInstance(result["messages"][1], dict)
        self.assertIn("role", result["messages"][1])
        self.assertIn("content", result["messages"][1])


    def test_ingest_with_both_order_id_and_email(self):
        """Test that email is NOT extracted when order_id is found"""
        state = {
            "ticket_text": "My speaker is not working ORD1002 contact alice@example.com",
            "order_id": None,
            "customer_email": None,
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        # Order ID should be extracted
        self.assertEqual(result["order_id"], "ORD1002")
        # Email should NOT be extracted when order_id is found
        self.assertIsNone(result["customer_email"])
        # Should have 2 messages: user message + order_id extracted message
        self.assertEqual(len(result["messages"]), 2)

    def test_ingest_with_only_email(self):
        """Test that email IS extracted when order_id is NOT found"""
        state = {
            "ticket_text": "My product is broken, contact alice@example.com",
            "order_id": None,
            "customer_email": None,
            "messages": [],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

        result = ingest_node(state)

        # Order ID should not be found
        self.assertIsNone(result["order_id"])
        # Email should be extracted as fallback
        self.assertEqual(result["customer_email"], "alice@example.com")
        # Should have 3 messages: user message + no order_id + email extracted
        self.assertEqual(len(result["messages"]), 3)


if __name__ == "__main__":
    unittest.main()
