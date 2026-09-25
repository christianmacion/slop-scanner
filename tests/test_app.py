"""Runs app.py headlessly with Streamlit's AppTest, as a user would click it."""
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "streamlit not installed")
class App(unittest.TestCase):
    def setUp(self):
        self.at = AppTest.from_file("../app.py", default_timeout=30).run()

    def test_loads_without_errors(self):
        self.assertFalse(self.at.exception)

    def test_heavy_sample_scores_heavy(self):
        self.at.selectbox[0].select("Heavy slop (scores ~80+)").run()
        self.assertFalse(self.at.exception)
        self.assertTrue(any("HEAVY SLOP" in m.value for m in self.at.markdown))

    def test_clean_sample_scores_clean(self):
        self.at.selectbox[0].select("Clean human draft (scores low)").run()
        self.assertTrue(any(">CLEAN<" in m.value for m in self.at.markdown))


if __name__ == "__main__":
    unittest.main()
