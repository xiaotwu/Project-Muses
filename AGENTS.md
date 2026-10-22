# Project-Muses guidance

Project-Muses is the family introduction, GitHub Pages and release hub. The three child directories are independent Git submodules with their own histories and build pipelines.

- Polyhymnia (macOS) is the core product and UX reference; Erato (iOS) and Euterpe (Windows 11) adapt it to native platform constraints. Never claim platform parity without source and runtime evidence.
- Read each child repository's guidance before changing it. Preserve unrelated work and credential files.
- Publish Pages only from this repository. `docs/` is the public website; child docs remain technical documentation and policy sources.
- Build/sign/notarize in platform repositories. Aggregate already-published assets without rebuilding or changing bytes. Use platform-prefixed release tags and preserve prerelease status and installation restrictions.
- Keep app update checks platform-specific so a release for another OS cannot be offered as an update.
- Commit child work first, merge and push child main branches, then commit the updated submodule references here.
- Validate site links, generated iOS policy parity, release sync logic and relevant platform checks before publication.
- Never add automated-assistant attribution or co-author trailers to commits, tags or PRs.

## Linear project

- All Muses family work belongs exclusively to [Muses](https://linear.app/xiaotwu/project/muses-5e747ca2af19), project `P-XW-2` / UUID `c2f9c252-e1d1-4210-bbd5-15a5366b9d28`, team `XW`.
- Explicitly scope issue queries and issue/document creation to this project. Confirm existing issues belong to it before updating them; preserve issue identifiers, parent relationships, evidence and paused work.
- This includes this family hub, Polyhymnia, Erato and Euterpe. Do not use unrelated Linear projects or leave new Muses issues unassigned to a project.

## Public product copy

Root READMEs introduce the family or platform product only. Product-facing website pages use the same editorial scope and omit provider/tooling names (YouTube, YouTube Music, Google, ChatGPT and Codex). Keep development, workspace and publication instructions in separate engineering documents outside the published site. Preserve accurate feature/availability boundaries and necessary provider disclosures in privacy policies and terms. The iOS landing page is editorial; only its legal pages/styles are mirrored from platform policy output.
