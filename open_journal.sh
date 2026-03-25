#!/usr/bin/env bash
cd "$(dirname "$0")"
python .dev-tools/_app-journal/launch_ui.py --project-root "$(dirname "$0")"
