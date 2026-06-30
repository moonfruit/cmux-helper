import unittest
import cmuxhelper


class ParseSavedHostsTests(unittest.TestCase):
    def test_skips_blank_and_comment_lines(self):
        text = "app@10.1.2.34\n\n# a comment\n  dev@10.1.2.32  \n"
        self.assertEqual(
            cmuxhelper.parse_saved_hosts(text),
            ["app@10.1.2.34", "dev@10.1.2.32"],
        )

    def test_empty_input(self):
        self.assertEqual(cmuxhelper.parse_saved_hosts(""), [])


class ParseSshConfigTests(unittest.TestCase):
    def test_user_applied_and_wildcards_skipped(self):
        text = (
            "Host 10.1.2.34 10.1.2.35\n"
            "    User app\n"
            "    ProxyJump 10.1.2.57\n"
            "Host *\n"
            "    ControlMaster auto\n"
            "Host git.server\n"
            "    WarnWeakCrypto false\n"
        )
        self.assertEqual(
            cmuxhelper.parse_ssh_config(text),
            ["app@10.1.2.34", "app@10.1.2.35", "git.server"],
        )

    def test_empty_input(self):
        self.assertEqual(cmuxhelper.parse_ssh_config(""), [])


if __name__ == "__main__":
    unittest.main()
