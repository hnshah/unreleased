# Releasing

1. Bump `version` in `.claude-plugin/plugin.json`, `gemini-extension.json` and `skills/unreleased/SKILL.md` metadata; add the section to `CHANGELOG.md`
   (`tools/validate_pack.py` checks they agree).
2. `python3 -I tools/validate_pack.py && python3 -I -m unittest discover -s tests -p "test_*.py"`.
3. Tag and push: `git tag -a v0.1.0 -m "unreleased 0.1.0" && git push origin v0.1.0`.

The `release` workflow runs the tests, builds `dist/unreleased-<version>.zip` with `tools/package_release.py`,
takes the notes from the matching CHANGELOG section and publishes the GitHub release with the zip attached.
