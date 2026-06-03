# OCUDU AI Playground

Collection of skills, agents and other AI-related tools to use with OCUDU Project.

## Installation

### Claude Code (plugin marketplace)

Register this repo as a marketplace source:

```text
/plugin marketplace add git@gitlab.com:ocudu/ocudu_ai_playground.git        # latest main
/plugin marketplace add git@gitlab.com:ocudu/ocudu_ai_playground.git#1.0.0  # pin to a tag or branch
```

Now you can search for OCUDU skills inside Claude Code:

```text
/plugins
```

Or directly install **individual skills**:

```text
/plugin install ci-triage@ocudu-ai-playground
/plugin install analyze-pcap@ocudu-ai-playground
```

To get updates after the repo changes:

```text
/plugin marketplace update ocudu-ai-playground
```

You might need to run `/reload-plugins` after install / upgrade.

### Manual (symlink)

Clone the repo and run the install script. Symlinks stay in sync as you pull updates.

```bash
git clone git@gitlab.com:ocudu/ocudu_ai_playground.git
cd ocudu_ai_playground
./install.sh                  # installs to ~/.claude/skills/ by default
./install.sh /path/to/.claude # custom install target
```

You might need to restart Claude Code after adding skills.
