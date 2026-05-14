#!/bin/bash
ssh -o ConnectTimeout=5 -i ~/.ssh/id_ed25519 boris@10.66.0.6 "openclaw agent --agent inbox --message \"$*\""
