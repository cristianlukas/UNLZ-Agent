import asyncio
import importlib
import os
import tempfile
import unittest
from pathlib import Path


class NewbieEndpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_root = tempfile.mkdtemp(prefix="unlz-newbie-tests-")
        os.environ["UNLZ_PROJECT_ROOT"] = cls._tmp_root
        Path(cls._tmp_root, "data").mkdir(parents=True, exist_ok=True)
        import agent_server  # noqa: WPS433
        cls.srv = importlib.reload(agent_server)

    def test_onboarding_health_shape(self):
        payload = asyncio.run(self.srv.onboarding_health())
        self.assertIn(payload["status"], ("ready", "needs_attention"))
        self.assertIsInstance(payload.get("checks"), list)
        self.assertGreaterEqual(len(payload["checks"]), 4)
        for chk in payload["checks"]:
            self.assertIn("id", chk)
            self.assertIn("status", chk)
            self.assertIn(chk["status"], ("ok", "warning", "error"))

    def test_onboarding_fix_and_templates(self):
        fixed = asyncio.run(self.srv.onboarding_fix(self.srv.OnboardingActionRequest()))
        self.assertEqual(fixed.get("status"), "ok")

        templates = asyncio.run(self.srv.newbie_task_templates())
        self.assertIsInstance(templates, list)
        self.assertGreaterEqual(len(templates), 4)
        self.assertTrue(all("prompt_template" in t for t in templates))

    def test_profile_roundtrip(self):
        before = asyncio.run(self.srv.newbie_get_profile())
        self.assertIn("experience_level", before)

        saved = asyncio.run(
            self.srv.newbie_save_profile({"language": "es", "experience_level": "newbie", "detail_level": "simple"})
        )
        self.assertEqual(saved.get("status"), "ok")
        after = asyncio.run(self.srv.newbie_get_profile())
        self.assertEqual(after.get("experience_level"), "newbie")

    def test_health_center_shape(self):
        payload = asyncio.run(self.srv.health_center())
        self.assertIn("provider", payload)
        self.assertIn("rag_index_ready", payload)
        self.assertIn("recent_errors", payload)


if __name__ == "__main__":
    unittest.main()
