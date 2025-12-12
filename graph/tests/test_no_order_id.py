import unittest
import copy
from graph.nodes.no_order_id import no_order_id_node
from graph.TriageState import TriageState


class TestNoOrderIdNode(unittest.TestCase):
    """Test cases for the no_order_id_node function"""

    def setUp(self):
        """Set up test state before each test"""
        self.base_state = {
            "ticket_text": "My product is broken",
            "order_id": None,
            "customer_email": None,
            "messages": [{"role": "user", "content": "My product is broken"}],
            "issue_type": None,
            "evidence": None,
            "recommendation": None
        }

    def test_no_order_id_sets_recommendation(self):
        """Test that recommendation is set correctly"""
        result = no_order_id_node(self.base_state.copy())

        self.assertIsNotNone(result["recommendation"])
        self.assertIn("cannot proceed", result["recommendation"].lower())
        self.assertIn("Order ID", result["recommendation"])

    def test_no_order_id_adds_message(self):
        """Test that system message is added"""
        result = no_order_id_node(self.base_state.copy())

        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][1]["role"], "system")
        self.assertIn("Workflow stopped", result["messages"][1]["content"])
        self.assertIn("missing order_id", result["messages"][1]["content"])

if __name__ == "__main__":
    unittest.main()
