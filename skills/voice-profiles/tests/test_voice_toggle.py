#!/usr/bin/env python3
"""Tests for voice_toggle.py — per-agent voice state manager."""

import os
import sys
import json
import tempfile
import unittest

# Set up temp state file BEFORE importing voice_toggle
temp_fd, temp_path = tempfile.mkstemp(suffix='.json')
os.close(temp_fd)
os.environ['VOICE_STATE_FILE'] = temp_path

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Now import the module
import voice_toggle


class TestVoiceToggle(unittest.TestCase):
    """Test suite for voice_toggle module."""

    def setUp(self):
        """Reset state file between tests."""
        state_file = os.environ.get('VOICE_STATE_FILE', temp_path)
        if os.path.exists(state_file):
            os.remove(state_file)

    def tearDown(self):
        """Clean up temp file."""
        pass

    def test_default_is_off(self):
        """Unknown agent defaults to 'off'."""
        state = voice_toggle.get_state('unknown_agent')
        self.assertEqual(state, 'off')

    def test_set_on(self):
        """Setting state to 'on' persists."""
        voice_toggle.set_state('nurse', 'on')
        state = voice_toggle.get_state('nurse')
        self.assertEqual(state, 'on')

    def test_set_off(self):
        """Setting state to 'off' after 'on' persists."""
        voice_toggle.set_state('nurse', 'on')
        voice_toggle.set_state('nurse', 'off')
        state = voice_toggle.get_state('nurse')
        self.assertEqual(state, 'off')

    def test_toggle_off_to_on(self):
        """Toggle from default 'off' to 'on'."""
        result = voice_toggle.toggle('agent1')
        self.assertEqual(result, 'on')
        self.assertEqual(voice_toggle.get_state('agent1'), 'on')

    def test_toggle_on_to_off(self):
        """Toggle from 'on' back to 'off'."""
        voice_toggle.set_state('agent2', 'on')
        result = voice_toggle.toggle('agent2')
        self.assertEqual(result, 'off')
        self.assertEqual(voice_toggle.get_state('agent2'), 'off')

    def test_independent_agents(self):
        """Different agents have independent states."""
        voice_toggle.set_state('nurse', 'on')
        voice_toggle.set_state('guilya', 'off')

        self.assertEqual(voice_toggle.get_state('nurse'), 'on')
        self.assertEqual(voice_toggle.get_state('guilya'), 'off')

    def test_is_on(self):
        """is_on returns correct boolean."""
        # Default is off
        self.assertFalse(voice_toggle.is_on('agent3'))

        # After setting on
        voice_toggle.set_state('agent3', 'on')
        self.assertTrue(voice_toggle.is_on('agent3'))

        # After setting off
        voice_toggle.set_state('agent3', 'off')
        self.assertFalse(voice_toggle.is_on('agent3'))

    def test_set_state_invalid_raises_error(self):
        """Setting invalid state raises ValueError."""
        with self.assertRaises(ValueError):
            voice_toggle.set_state('agent', 'invalid')

    def test_set_state_case_insensitive(self):
        """State accepts 'on' and 'off' case-insensitively."""
        voice_toggle.set_state('agent', 'ON')
        self.assertEqual(voice_toggle.get_state('agent'), 'on')

        voice_toggle.set_state('agent', 'OFF')
        self.assertEqual(voice_toggle.get_state('agent'), 'off')


if __name__ == '__main__':
    unittest.main()
