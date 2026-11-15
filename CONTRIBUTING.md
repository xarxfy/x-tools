# Contributing

Thanks for looking! X-TOOLS is a small project run by one person, so please keep changes focused.

- **Bugs and ideas:** open an issue. For beta testing use the issue template *Beta test* and the
  [checklist](docs/beta-testing.md). Please never paste secrets (tokens, passwords, agent keys, install commands).
- **Security problems:** not as a public issue – see [SECURITY.md](SECURITY.md).
- **Code:** open a pull request against `main`. Small, one topic per PR. Run the tests first:

  ```sh
  cd backend && pip install -e ".[dev]" && pytest      # backend
  cd frontend && npm ci && npm run build               # frontend must build without TypeScript errors
  ```

  Set up of the dev servers: [docs/development.md](docs/development.md). There is no CI – tests run on your machine.
- **Documentation** lives in `docs/`; the GitHub wiki is generated from it (`docs/wiki/`), so edit the files, not the wiki.
  Texts of the UI are in `frontend/src/i18n/` (one JSON file per language).
- **Style:** read the code around your change and follow it. Comments explain *why*, not what. New behaviour gets a test.
- **Note on origin:** most of the code was written with an AI assistant. Contributions by hand or with AI are both fine –
  you are responsible for what you submit and should understand it.

By contributing you agree that your contribution is licensed under the project's [MIT license](LICENSE).
