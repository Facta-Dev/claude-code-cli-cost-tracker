# .claude — this repo's Claude Code kit

The playbooks live in the playbook repo, not here. Read them there; do not
restate or import them into this file.

| Playbook | Governs |
| --- | --- |
| [PLAYBOOK_CLAUDE_CODE.md](https://github.com/Facta-Dev/facta-playbook/blob/main/PLAYBOOK_CLAUDE_CODE.md) | the kit this repo must have |
| [PLAYBOOK_TESTS.md](https://github.com/Facta-Dev/facta-playbook/blob/main/PLAYBOOK_TESTS.md) | testing contract and gates |
| [PLAYBOOK_SECURITY.md](https://github.com/Facta-Dev/facta-playbook/blob/main/PLAYBOOK_SECURITY.md) | security contract, per-language profiles |

Runbook: [CLAUDE_CODE_ROUTING_MODELS_OLLAMA.md](https://github.com/Facta-Dev/facta-playbook/blob/main/CLAUDE_CODE_ROUTING_MODELS_OLLAMA.md)
— model tiers, the routing block, `~/.claude/settings.json`.

Repo-local kit files live next to this file: `agents/`, `skills/`, `commands/`,
`rules/`, `settings.json`. Verify the wiring with:

```bash
bash ~/facta-playbook/scripts/claude-kit/configure-repo.sh <repo> --check
```
