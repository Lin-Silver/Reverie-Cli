# Native conversation tokenizer notices

The offline text counter uses tiktoken-rs 0.12.1 with default features disabled.
Cargo.lock pins crate SHA-256 `2aeff724640cfe13037336ddf35befdffd2909cbdb65cf041cc8a4cf8c584cfa`.
The local crate archive and `.cargo_vcs_info.json` were checked against that identity;
its source revision is `72a5a800651a1cea1ad609292446ba02c80e3bcd`.

The published crate omits the repository LICENSE. The exact upstream text is retained
in [tiktoken-rs-LICENSE.txt](tiktoken-rs-LICENSE.txt), from Git blob
`39aa2a22b04e732499c3f3cf6df84f50215d8f5f`. It is MIT and retains Roger Zurawicki's notice.

The crate's `src/vendor_tiktoken.rs` identifies its vendored tiktoken implementation.
At the same source revision, `vendor/tiktoken` points to OpenAI tiktoken commit
`4e71bbe0c078468e00fefbf94b39849389f346e5` (the submodule records tag 0.13.0).
[tiktoken-LICENSE.txt](tiktoken-LICENSE.txt) preserves that commit's MIT license and
OpenAI / Shantanu Jain copyright, Git blob `83ed1036f70d4f419307e8a044a35e163cc35201`.
Both files were read from the respective upstream repositories, without rewriting their terms.

These files cover the tokenizer source notices. They are part of the binary's required
third-party materials; they do not substitute for a complete audit of Cargo.lock or
the Electron/Chromium and optional runtime distributions.

Sources: [tiktoken-rs LICENSE](https://github.com/zurawiki/tiktoken-rs/blob/72a5a800651a1cea1ad609292446ba02c80e3bcd/LICENSE),
[vendored commit](https://github.com/zurawiki/tiktoken-rs/tree/72a5a800651a1cea1ad609292446ba02c80e3bcd/vendor),
[tiktoken LICENSE](https://github.com/openai/tiktoken/blob/4e71bbe0c078468e00fefbf94b39849389f346e5/LICENSE).

## Browser file transfers

The workspace file boundary uses cap-std and cap-fs-ext 4.0.3, from Bytecode Alliance revision `b7acf8e8807fe3fab991884d2208b7e03d35a409`. The lockfile pins each downloaded package. The notices for the eleven added packages retain the upstream copyright and selected license texts, including the LLVM exception for winx. Identical texts share one entry. [Bundled notices](browser-file-transfer-notices.txt)
