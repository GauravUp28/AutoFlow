import unittest
from agent_b.constants import AUTH_KEYWORDS, CREATION_AUTH_KEYWORDS

class TestConstants(unittest.TestCase):
    def test_auth_keywords_non_empty(self):
        self.assertTrue(len(AUTH_KEYWORDS) > 5)

    def test_creation_subset(self):
        for kw in CREATION_AUTH_KEYWORDS:
            self.assertIn(kw, AUTH_KEYWORDS)

if __name__ == '__main__':
    unittest.main()
