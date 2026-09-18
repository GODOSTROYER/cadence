# Confirmation packet: 200 real corpus messages

Read the [shared annotation guide](../verified_sampling/README.md) and [prospective policy v2](../../docs/POLICY_V2.md) before labeling. The exact policy is frozen in [policy.snapshot.yaml](policy.snapshot.yaml).

Complete [human_labels.csv](human_labels.csv) from the customer text and policy alone, before model inference and without AI labels or system outputs. Preserve `id` and `text`; save a separate `completed_human_labels.csv`. Follow the shared guide's named human import/validation commands. The current worksheet is blank and no human labels, reply ratings or inference are claimed.

[SAMPLE.lock.json](SAMPLE.lock.json) binds the examples, policy and exposure registry. The preparer and metadata reviewer checked this partition programmatically without displaying its message texts. Do not edit locked examples or use confirmation results for tuning. Human reply-quality scoring comes later, using a separate blinded packet after inference.

This is an English, brand-replied, deduplicated 2017 corpus sample, disjoint from recorded/reconstructed exposures and the new calibration/challenge partitions. Some historical inspection IDs were not retained, so these cases cannot be certified never to have been inspected. Its results will not estimate all modern traffic or every language.
