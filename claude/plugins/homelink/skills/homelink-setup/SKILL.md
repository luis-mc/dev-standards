---
name: homelink-setup
description: Set up the network side of a product that has a website and a server in the user's home. Interview the owner about the product's home server, install types, allow-listed calls and devices, then write the product's HomeLink profile and a task list against the HomeLink kit requirements (HL-n). Use when the user starts or reviews a product that must be reachable from the internet and from the home LAN, asks how a web app should reach a home server, a Home Assistant, a NAS or a PC service, or invokes /luismc-homelink:homelink-setup.
model: opus
effort: medium
---

# HomeLink: setup

Design G, written once for every product: the website is static files; a control plane pairs homes and hands out 5-minute tokens; a home agent next to the product's service exposes only an allow-list, calls the control plane outbound only, and is reached through a tunnel when away and directly on the LAN when at home. The rules are the `HL-n` requirements in the HomeLink spec. **The kit is a draft and not built.** This skill only writes the product's profile and tasks. It builds nothing and registers nothing.

## Rules

- Ask everything in one AskUserQuestion batch (several calls when more than 4). Each question carries its own context. No guessing: an unanswered field stays "open" in the profile.
- Never buy, register or submit anything, and never write to a DNS zone, Cloudflare, Vercel or the Public Suffix List. A domain name is the owner's choice; leave it "not chosen yet" until they give it.
- Never send a message, issue or request in the owner's name. Drafts go in files under `docs/`.
- Read the product's own repo first (its home server, ports, existing hosts) and say what you found in two lines before asking.
- Do not copy the kit's rules into the profile. Cite the `HL-n` ID.

## Steps

1. **Read** the product repo: what runs in the home, how it is installed, its hostnames, how users sign in. Read the HomeLink spec if it is on this machine (home-automation repo, `docs/features/homelink/spec.md`).
2. **Ask** (one batch): what runs in the home (own server, Home Assistant, both); install types wanted now and later (Windows service, Linux, macOS, NAS, container, Home Assistant add-on); calls the browser needs (the allow-list); data that must stay on the LAN path; must it work with the internet down and for how long; devices (phone, wall tablet, smart TV, desktop browser); local secrets the agent would hold and where they come from; whether device sessions (HL-12) suit these devices.
3. **Write** `docs/features/<product>/homelink-profile.md` from `assets/homelink-profile.md`, filled with the answers, plus a numbered task list. Each task names the HL-n IDs it serves.
4. **Check** with the docs check of the project, if it has one.
5. **Report**: Done, Left for you (numbered; the domain name and anything that needs the owner's hand), What you can do now.

## What this skill does not do (yet)

Pairing, tunnel, certificate and agent code. They arrive with the kit. Until then the profile is the product's contract with it.
