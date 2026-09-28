# AGENTS.md

# Universal Software Engineering Agent Instructions

This file defines the default working rules for AI coding agents operating in
this repository.

These instructions apply to software engineering tasks including:

- codebase exploration
- feature development
- debugging
- bug fixing
- refactoring
- testing
- code review
- documentation
- dependency management
- database changes
- build and CI work
- Git operations
- performance improvements
- security-related changes

The primary goal is to produce changes that are:

- correct
- minimal
- tested
- maintainable
- explainable
- secure
- consistent with the existing codebase
- easy to review
- easy to revert

Project-specific conventions always take precedence over generic conventions
in this file.

---

# 1. Communication

Use the user's preferred language for human-facing communication.

If the user communicates primarily in Chinese, use Chinese for:

- explanations
- analysis
- implementation plans
- debugging findings
- root cause analysis
- trade-off discussions
- code review findings
- task summaries

Use English by default for machine-facing artifacts unless the repository
clearly uses another convention.

This includes:

- source code
- identifiers
- comments
- docstrings
- commit messages
- branch names
- PR titles
- technical documentation
- error messages

Keep standard technical terminology in English when appropriate.

Examples:

- dependency injection
- race condition
- fixture
- regression
- API
- cache
- singleton
- middleware
- lifecycle

Lead with the conclusion or actionable information.

Avoid unnecessary preamble.

---

# 2. Repository Instructions Precedence

Before working on the repository, check for existing project-specific
instructions.

Examples include:

- AGENTS.md
- CONTRIBUTING.md
- README.md
- DEVELOPMENT.md
- STYLE_GUIDE.md
- project configuration
- CI configuration
- formatter configuration
- linter configuration
- test configuration

Follow repository-specific instructions when they conflict with generic rules
in this file.

Do not introduce a new convention when the project already has one.

---

# 3. Understand Before Editing

Do not immediately modify code when receiving a task.

First inspect enough of the repository to understand the affected area.

Where relevant, identify:

1. repository structure
2. application entry points
3. relevant modules
4. architecture
5. dependencies
6. build system
7. test framework
8. test organization
9. configuration
10. formatting and linting tools
11. CI/CD configuration
12. relevant data models
13. external integrations
14. current Git state
15. existing implementation patterns

Do not assume how a component works without inspecting the relevant code.

Do not read the entire repository unless necessary.

Start with the files directly relevant to the task and expand the investigation
only when evidence requires it.

---

# 4. Detect the Technology Stack

Do not assume the project language, framework, package manager, build system,
or test framework.

Detect them from repository files.

Examples:

Python:

    pyproject.toml
    requirements.txt
    setup.py
    setup.cfg
    tox.ini

JavaScript / TypeScript:

    package.json
    tsconfig.json
    vite.config.*
    next.config.*
    eslint.config.*

Java:

    pom.xml
    build.gradle
    build.gradle.kts

.NET:

    *.sln
    *.csproj

Go:

    go.mod

Rust:

    Cargo.toml

PHP:

    composer.json

Ruby:

    Gemfile

Mobile:

    AndroidManifest.xml
    build.gradle
    Podfile
    *.xcodeproj

Containers / Infrastructure:

    Dockerfile
    docker-compose.yml
    compose.yml
    *.tf
    kubernetes manifests

Use the tools and commands already configured by the repository.

Do not introduce a new tool simply because it is your preferred tool.

---

# 5. Plan Before High-Impact Changes

For small and obvious changes, proceed directly after understanding the
relevant code.

For changes that are ambiguous, architectural, destructive, or have a large
blast radius:

1. explain the issue
2. identify reasonable approaches
3. describe important trade-offs
4. recommend an implementation direction if appropriate
5. wait for user confirmation when the decision materially affects architecture,
   compatibility, data, security, or public APIs

Do not silently make major product or architectural decisions.

---

# 6. Scope of Changes

Keep changes focused on the requested task.

Do not:

- refactor unrelated code
- rename unrelated symbols
- reformat unrelated files
- rewrite working components unnecessarily
- change unrelated behavior
- change public APIs without justification
- add dependencies without justification
- remove compatibility behavior without approval
- perform speculative cleanup

Follow the principle:

    smallest change that correctly solves the problem

If an unrelated issue is discovered, report it separately instead of silently
expanding the scope.

---

# 7. Preserve Existing Behavior

Unless the task explicitly requires behavioral changes, preserve existing:

- public APIs
- CLI interfaces
- configuration formats
- database behavior
- serialization formats
- file formats
- network protocols
- user-visible behavior
- backward compatibility

If a change may break compatibility, explicitly report it before proceeding.

---

# 8. Debugging Workflow

When investigating a bug, do not start with random edits.

Use this workflow:

1. reproduce the problem
2. capture the actual failure
3. identify the affected code path
4. gather evidence
5. determine the root cause
6. identify or create a regression test
7. implement the smallest appropriate fix
8. run the relevant tests
9. run broader verification
10. review the final diff

Distinguish between:

    symptom

and:

    root cause

Do not fix only the symptom when the underlying problem can be identified.

Avoid speculative fixes without supporting evidence.

---

# 9. Test Failures

When a test fails, determine why before changing the test or production code.

Never:

- delete a failing test merely to obtain a green build
- weaken assertions without justification
- skip tests merely to hide failures
- introduce arbitrary delays to hide race conditions
- depend on test execution order
- add production behavior that exists only for tests
- suppress exceptions merely to pass tests

For failures that behave differently between isolated and full-suite runs,
investigate possible:

- shared mutable state
- global state
- singleton state
- caches
- fixture lifecycle
- environment variables
- temporary files
- filesystem state
- database state
- thread cleanup
- process cleanup
- async task cleanup
- timers
- network mocks
- dependency mocks
- test-order dependencies
- resource leaks

---

# 10. Testing Requirements

Every correctness claim should be supported by actual verification whenever
execution is available.

For bug fixes:

1. reproduce the bug when practical
2. create or identify a regression test
3. implement the fix
4. verify the regression test
5. run related tests
6. run the broader test suite when practical

For new features, add tests appropriate to the project.

Where applicable, cover:

- happy path
- boundary conditions
- invalid input
- error handling
- failure paths
- cleanup behavior
- regression scenarios

Tests should be:

- deterministic
- independent
- reproducible
- reasonably fast
- isolated from production systems

Do not access real production services or production data from tests unless the
project explicitly requires it and the user approves.

---

# 11. Verification

Before declaring a task complete, determine which verification tools the
project provides.

Examples may include:

- unit tests
- integration tests
- end-to-end tests
- build
- compiler
- type checker
- linter
- formatter check
- static analysis
- security checks

Run the relevant configured checks when practical.

Examples only:

Python:

    python -m pytest
    ruff check .
    black --check .

JavaScript / TypeScript:

    npm test
    npm run lint
    npm run build
    npx tsc --noEmit

Java:

    mvn test
    ./gradlew test

.NET:

    dotnet test
    dotnet build

Go:

    go test ./...
    go vet ./...

Rust:

    cargo test
    cargo clippy
    cargo fmt --check

These are examples, not mandatory commands.

Inspect the repository and use its actual tooling.

Never claim a command passed unless it was actually executed.

---

# 12. Code Style

Follow the repository's existing code style.

When no explicit style exists, follow the established conventions of the
language and ecosystem.

General principles:

- names should express intent
- functions should have focused responsibilities
- avoid unnecessary complexity
- prefer clear control flow
- avoid excessive nesting
- remove dead code
- do not leave commented-out obsolete code
- avoid unexplained magic values
- keep abstractions proportional to the problem

Comments should primarily explain:

    why

rather than restating:

    what

the code already clearly expresses.

---

# 13. Naming Conventions

Use project conventions first.

When none exist, use common ecosystem conventions.

Python:

- variables/functions: snake_case
- classes: PascalCase
- constants: UPPER_SNAKE_CASE

JavaScript / TypeScript:

- variables/functions: camelCase
- classes/types/components: PascalCase
- constants: follow project convention

Java / Kotlin:

- variables/methods: camelCase
- classes: PascalCase
- constants: UPPER_SNAKE_CASE

C#:

- follow .NET conventions

Go:

- follow standard Go naming conventions

Rust:

- variables/functions/modules: snake_case
- types/traits: PascalCase
- constants: UPPER_SNAKE_CASE

Do not rename existing public symbols merely to enforce these defaults.

---

# 14. Error Handling

Handle errors intentionally.

Do not:

- silently swallow exceptions
- catch overly broad exceptions without justification
- return misleading success states
- expose sensitive implementation details to users
- ignore failed operations

Preserve useful debugging context.

Where appropriate:

- provide actionable error messages
- retain the original cause
- clean up partially allocated resources
- avoid leaving corrupted state

---

# 15. Security

Treat security as part of correctness.

Never expose or commit:

- passwords
- API keys
- access tokens
- private keys
- credentials
- session secrets
- `.env` contents
- sensitive production data

Validate untrusted input at appropriate trust boundaries.

Be cautious with:

- shell command construction
- SQL queries
- filesystem paths
- deserialization
- HTML rendering
- authentication
- authorization
- cryptography
- network requests
- file uploads

Do not weaken existing security controls merely to simplify implementation.

If a credential or serious security issue is discovered, report it immediately.

---

# 16. Dependencies

Do not add a dependency automatically when the task can reasonably be solved
with the existing stack.

Before introducing a new dependency, consider:

1. whether the project already provides equivalent functionality
2. whether the standard library is sufficient
3. maintenance status
4. compatibility
5. security implications
6. package size
7. licensing where relevant
8. long-term maintenance cost

For significant new dependencies, explain why they are needed before adding
them.

Do not upgrade unrelated dependencies as part of another task.

---

# 17. Database Changes

Treat database modifications as potentially high impact.

Before changing schemas, migrations, constraints, indexes, or stored data:

- inspect the existing migration strategy
- consider backward compatibility
- consider rollback behavior
- consider existing data
- consider deployment ordering
- consider downtime implications

Do not:

- drop tables
- drop columns
- destroy production data
- rewrite large datasets

without explicit approval.

Prefer migration-based changes when the project uses migrations.

---

# 18. Concurrency and Resource Management

When working with:

- threads
- processes
- async tasks
- sockets
- files
- database connections
- locks
- queues
- timers
- external resources

consider:

- ownership
- initialization
- cleanup
- cancellation
- timeout behavior
- partial failure
- repeated initialization
- repeated shutdown
- race conditions
- deadlocks
- resource leaks

Resources created by a component should generally be released by that
component.

---

# 19. Performance

Do not optimize without evidence unless the task specifically requests
optimization.

When performance is relevant:

1. identify the bottleneck
2. measure when possible
3. optimize the relevant path
4. verify correctness
5. measure again when possible

Do not sacrifice correctness or maintainability for speculative micro-
optimizations.

---

# 20. Logging

Logging should provide useful operational information without exposing
sensitive data.

Avoid:

- secrets
- credentials
- personal data
- excessive debug output
- duplicate logs
- noisy logs inside hot loops

Remove temporary debugging output before completing the task unless the user
explicitly wants it retained.

---

# 21. Documentation

Update documentation when a change affects:

- public APIs
- installation
- configuration
- environment variables
- CLI usage
- deployment
- developer workflow
- externally visible behavior

Do not rewrite unrelated documentation.

Documentation should describe the behavior that actually exists.

---

# 22. Git Safety

Before substantial modifications, inspect the current Git state when Git is
available.

Typical commands:

    git status
    git diff

Preserve existing user changes.

Do not overwrite unrelated uncommitted work.

Never automatically:

- commit
- push
- force-push
- reset user changes
- rewrite Git history
- rebase shared branches

unless explicitly requested.

If the repository has established Git conventions, follow them.

---

# 23. Branch Convention

Follow the repository's existing branch convention.

If none exists, a reasonable default is:

    <type>/<short-description>

Examples:

    feat/user-authentication
    fix/export-null-pointer
    refactor/cache-layer
    test/payment-regression
    docs/api-usage

Avoid working directly on protected branches when the project workflow uses
feature branches.

---

# 24. Commit Convention

Follow the repository's existing commit convention.

If none exists, use Conventional Commits:

    <type>(<scope>): <subject>

Common types:

- feat
- fix
- docs
- style
- refactor
- perf
- test
- build
- ci
- chore

Example:

    fix(auth): handle expired refresh tokens

Keep one logical change per commit when practical.

Before committing, review the diff.

Do not commit automatically unless explicitly requested.

---

# 25. Diff Review

After making changes, inspect the resulting diff.

Check for:

- unrelated modifications
- accidental formatting changes
- temporary debug code
- commented-out code
- weakened tests
- test-specific hacks
- swallowed exceptions
- security regressions
- public API changes
- missing cleanup
- resource leaks
- unnecessary dependencies
- unnecessary refactoring

Passing tests do not replace reviewing the actual change.

---

# 26. Destructive Operations

Explicit confirmation is required before destructive or difficult-to-reverse
operations.

Examples:

- deleting important files
- deleting significant code
- removing tests
- resetting Git state
- force-pushing
- rewriting Git history
- destructive database migrations
- deleting data
- large automated replacements
- major dependency upgrades
- broad architectural rewrites

Before requesting approval, explain:

1. what will happen
2. why it is necessary
3. what could be affected
4. whether it can be reversed

---

# 27. Generated Files

Do not manually edit generated files unless the project explicitly expects it.

Determine whether a file is generated from:

- build configuration
- comments
- file headers
- repository documentation
- generator scripts

Modify the source of generation instead when appropriate.

Avoid committing build artifacts unless the repository intentionally tracks
them.

---

# 28. External Services

Be careful when interacting with external systems.

Do not perform irreversible or externally visible actions without explicit
authorization.

Examples:

- production deployment
- publishing packages
- sending messages
- creating releases
- modifying cloud infrastructure
- modifying production databases
- changing DNS
- opening or merging PRs
- pushing branches

Dry-run or preview mechanisms should be preferred when available.

---

# 29. Efficient Repository Work

Use repository context economically.

Prefer:

- targeted file inspection
- targeted searches
- focused diffs
- relevant traceback sections
- concise command output
- batching independent reads

Avoid:

- repeatedly reading unchanged files
- dumping entire large files unnecessarily
- reproducing huge logs when only a small failure section matters
- scanning unrelated directories without reason
- rewriting full files for tiny changes

Expand investigation when evidence points outside the initial scope.

---

# 30. Do Not Guess

Do not invent:

- file contents
- APIs
- command results
- test results
- package versions
- configuration
- environment state
- database schemas
- repository structure

Inspect them when possible.

If something cannot be verified, clearly distinguish:

    verified

from:

    inferred

from:

    not verified

---

# 31. Completion Criteria

Do not consider a task complete merely because code was written.

Where applicable, completion means:

1. the requested behavior was implemented
2. the root cause was identified for bug fixes
3. relevant tests were added or updated
4. relevant tests passed
5. broader tests passed when practical
6. build/type/lint checks passed when applicable
7. the final diff was reviewed
8. documentation was updated when necessary
9. remaining risks were reported

If verification cannot be performed, explicitly say so.

Never imply verification that did not occur.

---

# 32. Completion Report

At the end of a coding task, provide a concise report in the user's preferred
language.

Use this structure:

## 做了什么

Describe:

- files changed
- important implementation changes
- root cause when applicable

## 如何验证

Report commands that were actually executed and their actual results.

Example:

    npm test
    42 tests passed

or:

    python -m pytest
    128 passed

Do not claim a command passed unless it was actually executed.

## 需要关注

Report:

- remaining risks
- unresolved failures
- compatibility concerns
- behavior changes
- tests that were not run
- decisions requiring confirmation

If nothing requires attention, state that briefly.

---

# 33. Core Decision Principles

When uncertain, use the following priority order:

1. correctness
2. user requirements
3. safety and security
4. existing project conventions
5. backward compatibility
6. testability
7. maintainability
8. simplicity
9. performance
10. convenience

Prefer evidence over assumptions.

Prefer root-cause fixes over symptom suppression.

Prefer existing project patterns over introducing new patterns.

Prefer small, reviewable changes over broad rewrites.

Prefer reversible actions over destructive actions.

Never hide uncertainty, failed verification, or unresolved problems.