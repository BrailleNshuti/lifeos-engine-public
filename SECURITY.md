# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability**. Please do not open a public issue for a security problem.

Include what you found, the steps to reproduce it, and the version (`lifeos --version`).

This is a one-person project. I aim to answer within 7 days and to fix confirmed problems in the next release.

## What counts

- The privacy guard (`lifeos guard`) missing a secret or personal data it is meant to catch.
- Error output or logs leaking credentials (`redact_error` gaps).
- Anything that makes the engine act in the world (send, buy, post, delete) without an explicit yes.

## Supported versions

Only the latest release.
