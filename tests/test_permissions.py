import unittest
from permissions import Risk, classify_command

class PermissionTests(unittest.TestCase):
    def test_risks(self):
        self.assertEqual(classify_command("ls"), Risk.NORMAL)
        self.assertEqual(classify_command("sudo apt install x"), Risk.PRIVILEGED)
        self.assertEqual(classify_command("rm -rf folder"), Risk.DESTRUCTIVE)

if __name__ == "__main__":
    unittest.main()
