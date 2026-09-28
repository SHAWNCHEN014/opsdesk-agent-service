# Third-party components

The root MIT licence applies to newly authored OpsDesk code, documentation, UI, Skills and synthetic guidance. It does not relicense dependencies, model weights, containers or the reference prototype.

Installed Python distributions are pinned in `requirements.txt`. Their original licence texts and metadata are preserved under [third-party](third-party/inventory.json), with file hashes. Run `python scripts/archive_licenses.py` in the project environment to reproduce the inventory. These notices must stay with a redistributed source bundle. Metadata is recorded as supplied by each distribution; consult its actual licence files when redistributing that component.

Runtime components downloaded separately:

| Component | Purpose | Upstream terms |
| --- | --- | --- |
| Ollama | Local inference and embeddings | [Official repository and MIT licence](https://github.com/ollama/ollama) |
| Qwen3-8B | Structured intake, advisory priority, draft and review | [Official model card, Apache-2.0](https://huggingface.co/Qwen/Qwen3-8B) |
| nomic-embed-text-v2-moe | Multilingual embedding vectors | [Official model card, Apache-2.0](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe) |
| MySQL 8.0 container | Persistent relational database | [Official source and GPL-2.0](https://github.com/mysql/mysql-server/tree/8.0) |
| Redis 7.2 container | Short-lived conversation cache | [Official 7.2 source and BSD licence](https://github.com/redis/redis/tree/7.2) |

No weights, upstream Python package binaries, Docker images or third-party music are included in this repository. Amazon and Alexa are third-party names used only to describe the intended competition track and simulated interface; there is no official integration or endorsement.
