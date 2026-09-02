# Workflow Rules

## Git checkpoints

After every safe, working checkpoint — a file fix, a feature that passes verification, a dependency update, any meaningful incremental progress — create a git commit before moving to the next task.

- Stage only the files changed in that step (never `git add .` blindly)
- Write a short, descriptive commit message
- Never commit `.env` or any file containing secrets
- Never force-push or amend pushed commits
