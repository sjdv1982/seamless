"""Focused shareserver plan steps 0–1 verification; no runtime share API required.

Run with the seamless1 conda interpreter from any directory. This deliberately
checks the documentation contract before the implementation phases begin.
"""

import json
from pathlib import Path
import re
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs/agent"
WORKFLOW = REPO.parent / "seamless-workflow"


class SharesContractDocs(unittest.TestCase):
    def test_committed_slot_preconditions(self):
        """Step 0: per-driver slots and pacing exist in committed code."""
        def committed(path):
            return subprocess.check_output(
                ["git", "-C", str(WORKFLOW), "show", "HEAD:" + path], text=True
            )

        graph = committed("seamless_workflow/graph.py")
        runtime = committed("seamless_workflow/attachments/runtime.py")
        self.assertRegex(graph, r"attachments:\s*dict\s*=\s*field\(")
        self.assertIn("node.attachments[spec.driver]", runtime)
        self.assertIn("self._mount_sessions[(path, spec.driver)]", runtime)
        self.assertRegex(runtime, r"DELIVERY_INTERVAL\s*=\s*2\s*/\s*3")
        self.assertIn("session.last_delivery_at + DELIVERY_INTERVAL", runtime)
        subprocess.check_output(
            ["git", "-C", str(WORKFLOW), "cat-file", "-e",
             "HEAD:tests/test_attachment_slots.py"]
        )
        attachments = subprocess.check_output(
            ["git", "-C", str(REPO), "show",
             "HEAD:docs/agent/contracts/attachments.md"], text=True
        )
        self.assertIn("**widget** slot", attachments)
        self.assertIn("2/3 second apart", attachments)

    def test_plan_and_full_contract_sections(self):
        """Steps 0–1: checked-in plan and complete Appendix A page."""
        plan = (REPO / "plans/shareserver-plan.md").read_text()
        self.assertIn("## Appendix A", plan)
        self.assertIn("## Appendix B", plan)
        draft = plan.split("````markdown\n", 1)[1].split("\n````", 1)[0]
        contract = (DOCS / "contracts/shares.md").read_text()
        for heading in re.findall(r"^#{1,3} .+$", draft, re.MULTILINE):
            with self.subTest(heading=heading):
                self.assertIn(heading, contract)
        for ruling in ("0.0.0.0", "5813", "?marker=n", "409", "0.6",
                       "shares=False", "ctx.shares.namespace", "openapi.json",
                       "seamless-client.js", "before the cell has taken the value",
                       "share()", "returns `None`"):
            with self.subTest(ruling=ruling):
                self.assertIn(ruling, contract)

    def test_existing_contract_pages(self):
        """Appendix B: cross-page contract additions are present."""
        expectations = {
            "attachments.md": ("share", "ShareDriver", "ctx.a.share", "serialized"),
            "cells.md": ("share", 'ctx.a["share"]'),
            "workflow-context.md": ("shares", "shares=True", "0.6"),
            "mounts.md": ("0.6", "share"),
            "widgets.md": ("share",),
        }
        for page, phrases in expectations.items():
            content = (DOCS / "contracts" / page).read_text()
            for phrase in phrases:
                with self.subTest(page=page, phrase=phrase):
                    self.assertIn(phrase, content)

    def test_registration_and_generated_index(self):
        """Step 1: shares, widgets and streaming registered in all four lists."""
        registrations = [DOCS / "README.md", DOCS / "index.md",
                         DOCS / "config/mkdocs.yml", REPO / "mkdocs.yml"]
        pages = ("shares", "widgets", "streaming")
        for registration in registrations:
            text = registration.read_text()
            for page in pages:
                with self.subTest(registration=registration, page=page):
                    self.assertIn("contracts/" + page + ".md", text)
        index = json.loads((DOCS / "index.json").read_text())
        for page in pages:
            self.assertIn("contracts/" + page + ".md", index["topics"]["contracts"])


if __name__ == "__main__":
    unittest.main()
