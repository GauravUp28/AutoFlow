import unittest
from autoflow.brand_utils import extract_brands

class TestBrandUtils(unittest.TestCase):
    def test_capitalized_and_in_phrase(self):
        task = "Create a new project in Linear and sync with Notion"
        brands = extract_brands(task)
        self.assertIn('linear', brands)
        self.assertIn('notion', brands)

    def test_lowercase_ecosystem(self):
        task = "Search for react in npm"
        brands = extract_brands(task)
        self.assertIn('npm', brands)

    def test_limit(self):
        task = "Integrate Linear Notion GitHub npm pipeline"
        brands = extract_brands(task)
        self.assertLessEqual(len(brands), 3)

    def test_empty(self):
        self.assertEqual(extract_brands(""), [])

if __name__ == '__main__':
    unittest.main()
