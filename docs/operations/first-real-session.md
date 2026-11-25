[Documentation](../README.md) › [Setup and operations](README.md) › The first session on the real gateway

# The first session on the real gateway

A checklist for the first time the application calls the real Databricks AI Gateway. Until this session has
been run, everything the application has shown comes from the [fake gateway](fake-gateway.md). It is written
for the person who holds the gateway token and runs the commands.

> **Note:** steps 3 and 4 saturate a model on purpose and slow every other application that shares the
> endpoint while they run. Run them only when the owner of the endpoint has agreed to it. Use fictional files
> only; the samples that ship with the application are fictional.

## Before you begin

- [Local setup](local-setup.md) is complete and `gateway.base_url` points at the real endpoint.
- The token is in the environment, not in a file.

## The steps

1. `python -m doc_engine preflight`. Fix anything it reports. It also sends each model one small image; if a
   model refuses it, set `worker.send_images_as: pdf`.
2. One job from the UI: open **Medical record summary**, **Test run**, the 24-page sample. Expect no rejections.
   Then one run each of **Compare two medication lists** and **Check an invoice against its order** (7 calls in
   total, a few cents). These are the first time the prompts for several files meet a real model: check that the
   differences found are the planted ones (listed in `doc_engine/samples.py`) and that the page references open
   the right page of the right file. Then run the invoice flow once more with **Price tolerance** set to
   10 and **Accept delivery charges** set to Yes: the monitor arm price (68.50 against 62.50) and the delivery
   charge should no longer be reported, and the desk frame quantity still should.
3. `python -m doc_engine probe bucket --model haiku --dry-run`, then with `--confirm-saturation`. Repeat for `opus`.
   The probe saturates that model on purpose (at most about $0.34 for Haiku and about $14 for Opus at the prices in `config.example.yaml`, less if it stops early; `--dry-run` prints the figure).
   Bring back the files it writes under `results/`.
4. Ten jobs: Activity, 10 interactive jobs on the 150-page sample, or
   `python -m doc_engine load --flow flow_sample_medical --document doc_sample_medical_150 --jobs 10 --confirm-saturation`.
5. Bring back the printed summaries. `python -m doc_engine export --job ID --out DIR` gives the raw rows.

A bucket probe measures the room the bucket had when the run started, so run one only when nothing has used
that model for a while. How long the gateway takes to recover from a saturating run is not yet known: on
2026-11-25 a second Haiku probe 20 minutes after the first found far less room. Allow 30 minutes or more.

Leave at least a minute between saturating runs: the ledger starts each process believing the
quota is as it last recorded it, and other applications' use is invisible to it.

## What to bring back

- The printed summary of every `load` and `probe` run, and the files the probe writes under `results/`.
- For each sample run: whether the differences found are the planted ones, and whether the page references
  open the right page of the right file.
- Anything [preflight](commands.md) reported, especially about image input and the "thinking off" form of
  each model.

These results replace the **Not yet confirmed** notes throughout the documentation, and the table in
[Limits and what is not confirmed](limits.md).

## See also

- [Commands](commands.md): every option of `preflight`, `probe` and `load`
- [Settings](settings.md): where the measured limits of each model go
- [Troubleshooting](troubleshooting.md): what to do when a step here fails
- [The quota ledger](../how-it-works/quota-ledger.md): what the bucket probe measures and why
