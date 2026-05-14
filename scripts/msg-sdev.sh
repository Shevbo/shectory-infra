#!/bin/bash
ssh -o ConnectTimeout=5 -i ~/.ssh/id_ed25519 shevbo@10.66.0.4 "openclaw agent --agent inbox --message \"$*\""
