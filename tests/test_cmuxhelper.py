import json
import os
import tempfile
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


class CollectHostsTests(unittest.TestCase):
    def test_merges_and_dedups_preserving_order(self):
        with tempfile.TemporaryDirectory() as d:
            saved = os.path.join(d, "saved_hosts")
            config = os.path.join(d, "config")
            with open(saved, "w") as f:
                f.write("app@10.1.2.34\ndev@10.1.2.32\n")
            with open(config, "w") as f:
                f.write("Host 10.1.2.34\n    User app\nHost newbox\n    User gpp\n")
            self.assertEqual(
                cmuxhelper.collect_hosts(saved, config),
                ["app@10.1.2.34", "dev@10.1.2.32", "gpp@newbox"],
            )

    def test_missing_files_return_empty(self):
        self.assertEqual(
            cmuxhelper.collect_hosts("/no/such/saved", "/no/such/config"),
            [],
        )


class AliasTests(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        self.assertEqual(cmuxhelper.load_aliases("/no/such/aliases.json"), {})

    def test_load_corrupt_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            with open(p, "w") as f:
                f.write("not json{")
            self.assertEqual(cmuxhelper.load_aliases(p), {})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "aliases.json")
            data = {"app@h": {"alias": "生产", "tags": ["prod"]}}
            cmuxhelper.save_aliases(p, data)
            self.assertEqual(cmuxhelper.load_aliases(p), data)

    def test_apply_sets_entry(self):
        out = cmuxhelper.apply_alias({}, "app@h", " 生产A ", [" prod ", "", "app"])
        self.assertEqual(out, {"app@h": {"alias": "生产A", "tags": ["prod", "app"]}})

    def test_apply_empty_removes_entry(self):
        out = cmuxhelper.apply_alias({"app@h": {"alias": "x"}}, "app@h", "  ", ["", " "])
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
