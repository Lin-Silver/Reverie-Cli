#!/usr/bin/env node
// reverie-motion entry point. Kept minimal on purpose: Reverie CLI's command
// policy inspects the entry script it runs; the implementation lives in ../lib.
import { main } from "../lib/cli.mjs";

const code = await main();
process.exitCode = code;
