"""Shareserver plan step 8: documentation discoverability and usable examples.

Run with the seamless1 interpreter. This checks published guidance, not runtime
behavior, and does not execute the examples or open an endpoint.
"""
import ast
import json
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[3]


def shares_section(text):
    headings = list(re.finditer(r"^(#{1,3}) ([^\n]+)$", text, re.MULTILINE))
    for index, heading in enumerate(headings):
        if "share" not in heading.group(2).lower():
            continue
        depth = len(heading.group(1))
        end = next((h.start() for h in headings[index+1:]
                    if len(h.group(1)) <= depth), len(text))
        return text[heading.start():end]
    raise AssertionError("human workflow API has no discoverable shares heading")


class SharesHumanDocs(unittest.TestCase):
    def test_human_api_explains_configuration_transport_and_graph_loading(self):
        """Step 8: readers can install, expose, read/write and safely load shares."""
        page = (REPO / "docs/main/api/seamless-workflow.md").read_text()
        section = shares_section(page)
        requirements = {
            "optional HTTP dependency": r"seamless-workflow\[share\]",
            "writable Python entry point": r"\.share\([^\n]*readonly\s*=\s*False",
            "server configuration": r"shareserver\.configure",
            "host environment configuration": r"SEAMLESS_SHARE_HOST",
            "port environment configuration": r"SEAMLESS_SHARE_PORT",
            "runtime namespace": r"(?:ctx|context)\.shares\.namespace",
            "saved graph format": r"0\.6",
            "unknown-origin graph opt-out": r"shares\s*=\s*False",
            "conditional write marker": r"\?marker=",
            "conflict status": r"\b409\b",
            "API discovery": r"openapi\.json",
            "browser client": r"seamless-client\.js",
            "HTTP plus websocket": r"(?is)HTTP.*websocket|websocket.*HTTP",
            "null versus absent value": r"(?s)204.*404|404.*204",
        }
        for purpose, pattern in requirements.items():
            with self.subTest(purpose=purpose):
                self.assertRegex(section, pattern)
        self.assertRegex(section.lower(), r"raw|body|bodies")
        self.assertRegex(section, r"GET")
        self.assertRegex(section, r"PUT")

    def test_python_share_examples_parse_and_use_actual_entry_point(self):
        """Step 8: Python examples are syntactically usable and show Cell.share."""
        page = (REPO / "docs/main/api/seamless-workflow.md").read_text()
        blocks = re.findall(r"```python\s*\n(.*?)\n```", shares_section(page), re.DOTALL)
        self.assertTrue(blocks, "the shares guide needs a Python example")
        calls = []
        for block in blocks:
            tree = ast.parse(block)
            calls.extend(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute) and n.func.attr == "share")
        self.assertTrue(calls, "example must call a bound cell's share API")
        self.assertTrue(any(any(k.arg == "readonly" and isinstance(k.value, ast.Constant)
                               and k.value.value is False for k in call.keywords)
                            for call in calls), "example must demonstrate a writable share")

    def test_release_notes_make_feature_discoverable(self):
        """Step 8: release notes name the API and shipped HTTP/client discovery."""
        text = (REPO / "RELEASE-NOTES.md").read_text()
        self.assertRegex(text, r"Cell\.share|\.share\(")
        self.assertIn("openapi.json", text)
        self.assertIn("seamless-client.js", text)

    def test_authorizer_status_only_marks_shareserver_prerequisite_done(self):
        """Step 8: server prerequisite is shipped while authorizer remains a design."""
        text = (REPO / "plans/workflow-authorize.md").read_text()
        introduction = text.split("\n---", 1)[0]
        self.assertIn("Design-level plan for a future feature", introduction)
        self.assertIn("Not an implementation handoff", introduction)
        self.assertRegex(introduction.lower(), r"shareserver")
        self.assertNotRegex(introduction, r"shareserver[\s\S]{0,150}not yet present")
        self.assertRegex(introduction, r"shares\.md|shareserver-plan\.md")

    def test_share_contract_reports_current_implementation(self):
        """Step 8: the shipped contract no longer claims implementation is absent."""
        text = (REPO / "docs/agent/contracts/shares.md").read_text()
        self.assertNotIn("written ahead of the implementation", text)
        self.assertIn("test_contract_shares.py", text)
        self.assertIn("## Implementation status and current limitations", text)

    def test_generated_index_retains_share_contract_topic(self):
        """Step 8: generated navigation keeps the shipped share contract discoverable."""
        index = json.loads((REPO / "docs/agent/index.json").read_text())
        self.assertIn("contracts/shares.md", index["topics"]["contracts"])


if __name__ == "__main__":
    unittest.main()
