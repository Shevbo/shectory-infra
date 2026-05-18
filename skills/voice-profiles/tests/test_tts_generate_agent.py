#!/usr/bin/env python3
import sys, os, unittest
sys.path.insert(0, os.path.expanduser("~/skills/voice-profiles/scripts"))
import tts_flow

class TestGetPersonaForAgent(unittest.TestCase):
    def test_nurse_resolves_to_medsestra(self):
        persona = tts_flow.get_persona_for_agent("nurse")
        self.assertEqual(persona, "medsestra")

    def test_main_resolves_to_tank(self):
        persona = tts_flow.get_persona_for_agent("main")
        self.assertEqual(persona, "tank")

    def test_unknown_agent_falls_back_to_agent_id(self):
        persona = tts_flow.get_persona_for_agent("nonexistent-xyz-123")
        self.assertEqual(persona, "nonexistent-xyz-123")

if __name__ == "__main__":
    unittest.main()
