import tempfile
import unittest
from pathlib import Path
from config import settings
from tools.vision import inspect_image

class VisionTests(unittest.TestCase):
    def test_missing_image_file(self):
        result = inspect_image("non_existent_image.png")
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"].lower())

    def test_unsupported_image_extension(self):
        with tempfile.TemporaryDirectory(dir=settings.workspace) as d:
            p = Path(d) / "test.txt"
            p.write_text("not an image", encoding="utf-8")
            result = inspect_image(str(p))
            self.assertFalse(result["ok"])
            self.assertIn("unsupported", result["error"].lower())

if __name__ == "__main__":
    unittest.main()
