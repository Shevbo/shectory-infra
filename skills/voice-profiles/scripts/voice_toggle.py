#!/usr/bin/env python3
"""Per-agent voice on/off state manager.

State stored in ~/.openclaw/voice_state.json as { "nurse": "off", "guilya": "on", ... }
Default for unknown agents is "off".

Environment variable VOICE_STATE_FILE overrides the default path (useful for tests).

Public API:
  - get_state(agent_id: str) -> str       returns "on" or "off"
  - set_state(agent_id: str, state: str) -> None  raises ValueError for invalid state
  - toggle(agent_id: str) -> str          flips and returns new state
  - is_on(agent_id: str) -> bool          returns True if state is "on"

CLI:
  voice_toggle.py status <agent_id>      - prints "on" or "off"
  voice_toggle.py set <agent_id> on|off  - sets state, prints confirmation
  voice_toggle.py toggle <agent_id>      - flips and prints new state
  voice_toggle.py check <agent_id>       - exits 0 if on, exits 1 if off
"""

import os
import json
import sys
import fcntl
import shutil
import warnings
from pathlib import Path


def _get_state_file():
    """Get the path to the voice state file."""
    return os.environ.get('VOICE_STATE_FILE', os.path.expanduser('~/.openclaw/voice_state.json'))


def _load_state():
    """Load state from file. Returns empty dict if file doesn't exist."""
    state_file = _get_state_file()
    if not os.path.exists(state_file):
        return {}

    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        bak = state_file + '.bak'
        shutil.copy2(state_file, bak)
        warnings.warn(f"Corrupted voice_state.json backed up to {bak}, treating as empty.")
        return {}
    except IOError:
        return {}


def _save_state(state):
    """Save state to file, creating parent directories if needed."""
    state_file = _get_state_file()
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)

    tmp = state_file + '.tmp'
    with open(tmp, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(state, f, indent=2)
    os.replace(tmp, state_file)


def get_state(agent_id: str) -> str:
    """Get voice state for agent. Returns 'on' or 'off'."""
    state = _load_state()
    return state.get(agent_id, 'off')


def set_state(agent_id: str, state: str) -> None:
    """Set voice state for agent.

    Args:
        agent_id: Agent identifier
        state: 'on' or 'off' (case-insensitive)

    Raises:
        ValueError: If state is not 'on' or 'off'
    """
    normalized_state = state.lower()
    if normalized_state not in ('on', 'off'):
        raise ValueError(f"Invalid state: {state}. Must be 'on' or 'off'.")

    current = _load_state()
    current[agent_id] = normalized_state
    _save_state(current)


def toggle(agent_id: str) -> str:
    """Toggle voice state for agent. Returns new state ('on' or 'off')."""
    current_state = get_state(agent_id)
    new_state = 'off' if current_state == 'on' else 'on'
    set_state(agent_id, new_state)
    return new_state


def is_on(agent_id: str) -> bool:
    """Return True if voice is on for agent."""
    return get_state(agent_id) == 'on'


def _cli_status(agent_id: str) -> None:
    """CLI: Print current status."""
    state = get_state(agent_id)
    print(state)


def _cli_set(agent_id: str, state: str) -> None:
    """CLI: Set state and print confirmation."""
    try:
        set_state(agent_id, state)
        normalized = state.lower()
        print(f"Voice {normalized} for {agent_id}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cli_toggle(agent_id: str) -> None:
    """CLI: Toggle state and print new state."""
    new_state = toggle(agent_id)
    print(new_state)


def _cli_check(agent_id: str) -> None:
    """CLI: Exit 0 if on, 1 if off (for bash conditionals)."""
    sys.exit(0 if is_on(agent_id) else 1)


def main():
    """CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: voice_toggle.py <command> <agent_id> [state]", file=sys.stderr)
        print("Commands: status, set, toggle, check", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    agent_id = sys.argv[2]

    if command == 'status':
        _cli_status(agent_id)
    elif command == 'set':
        if len(sys.argv) < 4:
            print("Error: set requires state argument (on|off)", file=sys.stderr)
            sys.exit(1)
        _cli_set(agent_id, sys.argv[3])
    elif command == 'toggle':
        _cli_toggle(agent_id)
    elif command == 'check':
        _cli_check(agent_id)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
