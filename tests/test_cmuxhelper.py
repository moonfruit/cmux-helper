import json
import os
import tempfile
import unittest
from unittest import mock
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


class BuildItemsTests(unittest.TestCase):
    def test_item_without_alias(self):
        out = cmuxhelper.build_alfred_items(["app@h"], {})
        item = out["items"][0]
        self.assertEqual(item["title"], "app@h")
        self.assertEqual(item["arg"], "app@h")
        self.assertEqual(item["uid"], "app@h")
        self.assertEqual(item["match"], "app@h")
        self.assertIn("↵ ssh", item["subtitle"])
        self.assertEqual(item["mods"]["cmd"]["arg"], "app@h")
        self.assertEqual(item["mods"]["alt"]["arg"], "app@h")

    def test_item_with_alias_and_tags(self):
        aliases = {"app@h": {"alias": "生产A", "tags": ["prod", "app"]}}
        item = cmuxhelper.build_alfred_items(["app@h"], aliases)["items"][0]
        self.assertEqual(item["title"], "生产A  ·  app@h")
        self.assertEqual(item["autocomplete"], "生产A")
        self.assertEqual(item["match"], "app@h 生产A prod app")
        self.assertIn("#prod", item["subtitle"])


class CommandTests(unittest.TestCase):
    def test_cmd_ssh(self):
        self.assertEqual(
            cmuxhelper.cmd_ssh("app@h"),
            [["cmux", "ssh", "app@h"], ["open", "-a", "cmux"]],
        )

    def test_cmd_send_has_literal_newline(self):
        cmds = cmuxhelper.cmd_send("app@h", "workspace:1")
        self.assertEqual(cmds[0], ["cmux", "send", "--workspace", "workspace:1", "ssh app@h\\n"])
        self.assertEqual(cmds[1], ["open", "-a", "cmux"])

    def test_aliases_path_in_ssh_dir(self):
        self.assertEqual(
            cmuxhelper.aliases_path(),
            os.path.expanduser("~/.ssh/aliases.json"),
        )

    def test_main_filter_prints_json(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmuxhelper.main(["filter", ""])
        self.assertEqual(rc, 0)
        parsed = json.loads(buf.getvalue())
        self.assertIn("items", parsed)


class FilterItemsTests(unittest.TestCase):
    def _items(self):
        return cmuxhelper.build_alfred_items(
            ["app@10.1.2.34", "dev@10.1.2.32"],
            {"app@10.1.2.34": {"alias": "生产A", "tags": ["prod"]}},
        )["items"]

    def test_empty_query_returns_all(self):
        items = self._items()
        self.assertEqual(cmuxhelper.filter_items(items, ""), items)

    def test_whitespace_query_returns_all(self):
        items = self._items()
        self.assertEqual(cmuxhelper.filter_items(items, "   "), items)

    def test_substring_on_ip(self):
        out = cmuxhelper.filter_items(self._items(), "2.34")
        self.assertEqual([i["arg"] for i in out], ["app@10.1.2.34"])

    def test_matches_alias(self):
        out = cmuxhelper.filter_items(self._items(), "生产")
        self.assertEqual([i["arg"] for i in out], ["app@10.1.2.34"])

    def test_case_insensitive(self):
        out = cmuxhelper.filter_items(self._items(), "DEV")
        self.assertEqual([i["arg"] for i in out], ["dev@10.1.2.32"])

    def test_multiple_tokens_all_must_match(self):
        out = cmuxhelper.filter_items(self._items(), "dev 32")
        self.assertEqual([i["arg"] for i in out], ["dev@10.1.2.32"])

    def test_no_match_returns_empty(self):
        self.assertEqual(cmuxhelper.filter_items(self._items(), "zzz"), [])


class AppleScriptStrTests(unittest.TestCase):
    def test_keeps_unicode_literal(self):
        self.assertEqual(cmuxhelper._as_applescript("别名"), '"别名"')

    def test_escapes_quote_and_backslash(self):
        self.assertEqual(cmuxhelper._as_applescript('a"b\\c'), '"a\\"b\\\\c"')


class CmuxRunningTests(unittest.TestCase):
    def test_running_when_ping_exits_zero(self):
        with mock.patch.object(
            cmuxhelper.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as m:
            self.assertTrue(cmuxhelper.cmux_running())
        self.assertEqual(m.call_args[0][0], ["cmux", "ping"])

    def test_not_running_when_ping_nonzero(self):
        with mock.patch.object(
            cmuxhelper.subprocess, "run", return_value=mock.Mock(returncode=1)
        ):
            self.assertFalse(cmuxhelper.cmux_running())

    def test_not_running_when_cmux_missing(self):
        with mock.patch.object(
            cmuxhelper.subprocess, "run", side_effect=FileNotFoundError
        ):
            self.assertFalse(cmuxhelper.cmux_running())


class MainGateTests(unittest.TestCase):
    def test_connect_aborts_and_notifies_when_not_running(self):
        with mock.patch.object(cmuxhelper, "cmux_running", return_value=False), \
                mock.patch.object(cmuxhelper, "_run") as run, \
                mock.patch.object(cmuxhelper, "_notify") as notify:
            rc = cmuxhelper.main(["connect", "app@h"])
        run.assert_not_called()
        notify.assert_called_once()
        self.assertEqual(rc, 1)

    def test_connect_runs_when_running(self):
        with mock.patch.object(cmuxhelper, "cmux_running", return_value=True), \
                mock.patch.object(cmuxhelper, "_run") as run, \
                mock.patch.object(cmuxhelper, "_notify") as notify:
            rc = cmuxhelper.main(["connect", "app@h"])
        run.assert_called_once_with(cmuxhelper.cmd_ssh("app@h"))
        notify.assert_not_called()
        self.assertEqual(rc, 0)

    def test_send_aborts_when_not_running(self):
        with mock.patch.object(cmuxhelper, "cmux_running", return_value=False), \
                mock.patch.object(cmuxhelper, "_run") as run, \
                mock.patch.object(cmuxhelper, "_notify"):
            rc = cmuxhelper.main(["send", "app@h"])
        run.assert_not_called()
        self.assertEqual(rc, 1)


class RunTests(unittest.TestCase):
    def test_missing_command_does_not_raise_and_stops(self):
        attempted = []

        def fake_run(cmd, **kwargs):
            attempted.append(cmd[0])
            raise FileNotFoundError(cmd[0])

        with mock.patch.object(cmuxhelper.subprocess, "run", side_effect=fake_run):
            cmuxhelper._run([["cmux", "ssh", "x"], ["open", "-a", "cmux"]])

        # cmux missing -> reported, and `open` is not attempted afterwards
        self.assertEqual(attempted.count("cmux"), 1)
        self.assertNotIn("open", attempted)


if __name__ == "__main__":
    unittest.main()
