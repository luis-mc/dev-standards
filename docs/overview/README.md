---
id: overview
title: Overview
type: explanation
owner: owner
last_verified: 2026-10-31
---
# Overview

dev-standards is a repository of Claude Code plugins and the specs they enforce. The owner installs the plugins once per machine from the `dev-standards` marketplace. Claude Code sessions and agents in the owner's other projects then use them to set a project up, write specs, keep docs and status true, deliver work and review code.

## Mission

Make good practice mechanical. A rule that lives in a memory note gets forgotten. A rule that lives in a hook, a script or a spec gets applied every time.

## Users

- **The owner.** One person. They install the plugins, set the standards, and read the status artifacts instead of code or chat.
- **Claude Code sessions and agents in consuming projects.** They get the plugins' skills, hooks and agents, and they read the shipped specs as binding rules.

## Why it exists

Starting every project from a blank repo means forgetting something: CI, secret scanning, a test rule, a docs layout. Rules told to an agent in chat fade after a few turns. This repository keeps each rule in one place, versioned, with an ID that hooks, tests and other projects can cite.

## What it is not

- It is not a product. It has no users outside the owner's own projects.
- It is not a framework or a library that a project imports. A project gets copies of generated files and a Stack Profile, never a vendored spec.
- It does not choose vendors. The stack wizard shows which choices fit together; the owner picks.
- It does not write to git for you. Plugins write files in the working tree; the project commits when it chooses.
- It does not fix audit findings. The audit skills report; a human triages.

## Read next

- [The apps](apps.md)
- [How the parts fit](system.md)
- [Glossary](glossary.md)
- [Quality goals and constraints](quality.md)
