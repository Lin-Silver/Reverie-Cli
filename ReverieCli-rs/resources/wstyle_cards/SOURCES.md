# Bundled WStyle sources

The six Markdown cards are first-party Reverie assets, copied byte for byte from the final Python source at commit `070fa25`. They retain the repository MIT license. Rust embeds these bytes directly and never needs the Python package to install or load them.

| Card | Original Git blob |
|---|---|
| commercial-serial-engagement.md | c7b9882254d7e45782c12123bf7f7fcdda91d30c |
| delicate-prose.md | 9b7c64629a499b1fadcc431c501d4acb8ead979b |
| dual-heroines.md | 8c4182965be3be6dc4aa89a2f8ec5aaead2e43b9 |
| ensemble-heroines.md | caea5237e11c82b6220a038eaca52366d80dcc03 |
| gl-romance-beats.md | bb24afca88381cd7460b755e515fa2eaf562e5ed |
| isekai-subversion-comedy.md | 312dceaa8088c2ce25f742ad273cad320ef7874c |

Card identity uses NFC normalization validation and full Unicode default casefold. The frozen `unicode-normalization 0.1.26` tables implement Unicode 18; `caseless 0.2.2` uses Unicode 16. The fixture tests cover the Python application's current character set and representative casefold expansion. They do not establish complete equivalence between different Unicode table versions.
