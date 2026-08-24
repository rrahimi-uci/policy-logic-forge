# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting:
**Security → Report a vulnerability** on this repository. Include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof of concept if possible),
- any suggested remediation.

We aim to acknowledge reports within a few business days.

## Handling secrets

- **Never commit secrets.** The OpenAI API key and any config overrides
  belong in the gitignored `.env` and `config.json`, never in source control
  or a committed configuration file.
- Copy `.env.example` to `.env` and `config.example.json` to `config.json`,
  then fill in your own values locally.
- If a secret is ever committed, treat it as compromised: rotate the
  credential immediately and remove it from history.

## Scope and hardening notes

This is a CLI-and-library research pipeline with no server component: no UI,
no backend API, and no self-hosted service exposed to a network. Its only
external dependency is the OpenAI API, called with a key you supply.

- The pipeline reads and writes local files only (`compliance-files/`,
  `pipeline-output/`, `benchmarks/`); it does not open a network port.
- Documents you point the pipeline at are sent to the OpenAI API as part of
  extraction — do not run it over documents you are not authorized to send
  to a third-party model provider.
- Two of the four benchmark corpora (OPP-115, MAPP) are licensed for research
  use without a redistribution grant; see `README.md` "Data and licensing"
  before redistributing anything built from them.
